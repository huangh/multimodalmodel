"""Discovery and loading of hub scripts.

A "hub script" is an ordinary marimo notebook stored somewhere under the
scripts root. The hub scans that tree, reads each script's metadata *without
importing it*, and only executes a script when a user selects it.

Metadata lives in a PEP 723-style comment block at the top of the file, which
marimo preserves across saves and which is invisible to the notebook itself:

    # /// hub
    # title = "Route stop counts"
    # description = "Stops per route from a static GTFS feed."
    # tags = ["gtfs", "static"]
    # params = ["gtfs_dir"]
    # ///

Every field is optional. Without a block, the title falls back to the app
title passed to ``marimo.App(app_title=...)``, then the module docstring, then
a humanized filename.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tomllib
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from marimo import App

FRONTMATTER_OPEN = "# /// hub"
FRONTMATTER_CLOSE = "# ///"

#: Directories that never contain hub scripts.
SKIP_DIRS = frozenset({"__pycache__", ".ipynb_checkpoints", "__marimo__"})


class ScriptLoadError(RuntimeError):
    """Raised when a script file cannot be loaded as a marimo app."""


@dataclass(frozen=True)
class ScriptMeta:
    """Static metadata about a hub script, parsed without executing it."""

    script_id: str
    """Slash-separated path relative to the scripts root, without ``.py``."""

    path: Path
    title: str
    description: str = ""
    tags: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    mtime: float = 0.0
    error: str | None = None
    """Set when the file could not be parsed; the script is still listed."""

    @property
    def group(self) -> str:
        """Directory portion of the script id (``""`` for top-level scripts)."""
        head, _, _ = self.script_id.rpartition("/")
        return head

    @property
    def group_parts(self) -> tuple[str, ...]:
        return tuple(p for p in self.group.split("/") if p)

    @property
    def label(self) -> str:
        """Human-facing label used in the dropdown."""
        if self.group:
            return f"{self.group.replace('/', ' / ')} / {self.title}"
        return self.title

    def matches(self, query: str = "", tags: Iterable[str] = ()) -> bool:
        """True when the script matches a free-text query and all given tags."""
        wanted = {t.lower() for t in tags}
        if wanted and not wanted.issubset({t.lower() for t in self.tags}):
            return False
        q = query.strip().lower()
        if not q:
            return True
        haystack = " ".join(
            (self.script_id, self.title, self.description, *self.tags)
        ).lower()
        return all(term in haystack for term in q.split())


def _read_frontmatter(source: str) -> dict[str, Any]:
    """Parse the ``# /// hub`` TOML block from a script's leading comments."""
    lines: list[str] = []
    in_block = False
    for raw in source.splitlines():
        line = raw.strip()
        if not in_block:
            if line == FRONTMATTER_OPEN:
                in_block = True
            elif line and not line.startswith("#"):
                # Frontmatter must precede any code.
                break
            continue
        if line == FRONTMATTER_CLOSE:
            break
        if line.startswith("#"):
            lines.append(line[1:].removeprefix(" "))
        else:
            break
    if not lines:
        return {}
    try:
        return tomllib.loads("\n".join(lines))
    except tomllib.TOMLDecodeError:
        return {}


def _app_title_from_ast(tree: ast.Module) -> str | None:
    """Pull ``app_title`` out of a top-level ``marimo.App(...)`` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "App":
            continue
        for kw in node.keywords:
            if kw.arg == "app_title" and isinstance(kw.value, ast.Constant):
                value = kw.value.value
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return ()


def _humanize(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().capitalize()


def parse_script(path: Path, root: Path) -> ScriptMeta:
    """Build :class:`ScriptMeta` for ``path`` using static analysis only."""
    script_id = path.relative_to(root).with_suffix("").as_posix()
    mtime = path.stat().st_mtime
    source = path.read_text(encoding="utf-8")

    meta = _read_frontmatter(source)
    title = str(meta.get("title", "")).strip()
    description = str(meta.get("description", "")).strip()
    error: str | None = None

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
    else:
        if not title:
            title = _app_title_from_ast(tree) or ""
        doc = ast.get_docstring(tree) or ""
        if doc:
            head, _, rest = doc.strip().partition("\n")
            title = title or head.strip()
            description = description or rest.strip() or head.strip()

    return ScriptMeta(
        script_id=script_id,
        path=path,
        title=title or _humanize(path.stem),
        description=description,
        tags=_as_str_tuple(meta.get("tags")),
        params=_as_str_tuple(meta.get("params")),
        mtime=mtime,
        error=error,
    )


def iter_script_paths(root: Path) -> Iterator[Path]:
    """Yield candidate script files under ``root``, deepest-stable ordering."""
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name.startswith("_"):
            continue
        yield path


def discover_scripts(root: Path | str) -> list[ScriptMeta]:
    """Scan ``root`` and return metadata for every script, sorted by label."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        return []
    scripts = [parse_script(p, root) for p in iter_script_paths(root)]
    return sorted(scripts, key=lambda s: (s.group_parts, s.title.lower()))


def load_app_from_path(path: Path) -> App:
    """Load a marimo ``App`` from a file without polluting ``sys.modules``.

    Uses marimo's own static loader when available (it never executes cell
    bodies at import time) and falls back to a normal module import under a
    unique name so repeated loads stay independent.
    """
    try:
        from marimo._ast.load import load_app as _marimo_load_app
    except ImportError:  # pragma: no cover - very old marimo
        _marimo_load_app = None

    if _marimo_load_app is not None:
        app = _marimo_load_app(str(path))
        if app is None:
            raise ScriptLoadError(f"{path} does not contain any marimo cells")
        return app

    module_name = f"_hub_script_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ScriptLoadError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    app = getattr(module, "app", None)
    if app is None:
        raise ScriptLoadError(f"{path} does not define a module-level `app`")
    return app


@dataclass
class ScriptRegistry:
    """Cached view over the script tree.

    The cache is keyed on file mtime, so editing a script on disk makes the
    next :meth:`refresh` pick it up without restarting the server.
    """

    root: Path
    _scripts: dict[str, ScriptMeta] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        self.refresh()

    def refresh(self) -> list[ScriptMeta]:
        found = discover_scripts(self.root)
        self._scripts = {s.script_id: s for s in found}
        return found

    def all(self) -> list[ScriptMeta]:
        return sorted(
            self._scripts.values(), key=lambda s: (s.group_parts, s.title.lower())
        )

    def get(self, script_id: str) -> ScriptMeta:
        try:
            return self._scripts[script_id]
        except KeyError:
            raise KeyError(f"Unknown script: {script_id!r}") from None

    def search(self, query: str = "", tags: Iterable[str] = ()) -> list[ScriptMeta]:
        tags = tuple(tags)
        return [s for s in self.all() if s.matches(query, tags)]

    def tags(self) -> list[str]:
        return sorted({t for s in self._scripts.values() for t in s.tags})

    def groups(self) -> list[str]:
        return sorted({s.group for s in self._scripts.values() if s.group})

    def tree(self) -> dict[str, Any]:
        """Nested ``{dir: {...}, script_id: ScriptMeta}`` view of the tree."""
        root: dict[str, Any] = {}
        for script in self.all():
            node = root
            for part in script.group_parts:
                node = node.setdefault(part, {})
            node[script.path.stem] = script
        return root

    def load(self, script_id: str) -> App:
        """Load (or reload) the marimo app for ``script_id``.

        Always returns a fresh app so two viewers never share cell state.
        """
        meta = self.get(script_id)
        if not meta.path.exists():
            self.refresh()
            meta = self.get(script_id)
        return load_app_from_path(meta.path)
