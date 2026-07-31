"""Tests for hub script discovery."""

from pathlib import Path

import pytest

from multimodalmodel.hub.registry import (
    ScriptRegistry,
    _read_frontmatter,
    discover_scripts,
    load_app_from_path,
    parse_script,
)

NOTEBOOK = """# /// hub
# title = "Nice title"
# description = "What it does."
# tags = ["gtfs", "offline"]
# params = ["gtfs_path"]
# ///
import marimo

app = marimo.App(app_title="Ignored when frontmatter wins")


@app.cell
def _():
    x = 21
    return (x,)


@app.cell
def _(x):
    doubled = x * 2
    doubled
    return (doubled,)


if __name__ == "__main__":
    app.run()
"""

BARE_NOTEBOOK = '''"""Docstring title.

Longer explanation.
"""
import marimo

app = marimo.App(app_title="App title")


@app.cell
def _():
    y = 1
    return (y,)
'''


@pytest.fixture
def scripts_root(tmp_path: Path) -> Path:
    (tmp_path / "gtfs" / "static").mkdir(parents=True)
    (tmp_path / "gtfs" / "static" / "feed.py").write_text(NOTEBOOK)
    (tmp_path / "bare.py").write_text(BARE_NOTEBOOK)
    (tmp_path / "_hidden.py").write_text(NOTEBOOK)
    (tmp_path / "notes.md").write_text("not a script")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.py").write_text(NOTEBOOK)
    return tmp_path


def test_read_frontmatter_parses_toml_comment_block():
    meta = _read_frontmatter(NOTEBOOK)
    assert meta["title"] == "Nice title"
    assert meta["tags"] == ["gtfs", "offline"]


def test_read_frontmatter_absent_returns_empty():
    assert _read_frontmatter("import marimo\n") == {}


def test_discovery_skips_underscores_pycache_and_non_python(scripts_root: Path):
    ids = {s.script_id for s in discover_scripts(scripts_root)}
    assert ids == {"gtfs/static/feed", "bare"}


def test_frontmatter_metadata_wins_over_app_title(scripts_root: Path):
    meta = parse_script(scripts_root / "gtfs" / "static" / "feed.py", scripts_root)
    assert meta.title == "Nice title"
    assert meta.description == "What it does."
    assert meta.tags == ("gtfs", "offline")
    assert meta.params == ("gtfs_path",)
    assert meta.group == "gtfs/static"
    assert meta.label == "gtfs / static / Nice title"
    assert meta.error is None


def test_falls_back_to_app_title_then_docstring(scripts_root: Path):
    meta = parse_script(scripts_root / "bare.py", scripts_root)
    assert meta.title == "App title"
    assert "Longer explanation." in meta.description
    assert meta.group == ""


def test_humanized_filename_is_last_resort(tmp_path: Path):
    path = tmp_path / "my_cool_plot.py"
    path.write_text("import marimo\napp = marimo.App()\n")
    assert parse_script(path, tmp_path).title == "My cool plot"


def test_syntax_error_is_reported_not_raised(tmp_path: Path):
    path = tmp_path / "broken.py"
    path.write_text("def oops(:\n")
    meta = parse_script(path, tmp_path)
    assert meta.error is not None and "SyntaxError" in meta.error


def test_registry_search_by_query_and_tags(scripts_root: Path):
    registry = ScriptRegistry(scripts_root)
    assert [s.script_id for s in registry.search("nice")] == ["gtfs/static/feed"]
    assert [s.script_id for s in registry.search(tags=["offline"])] == [
        "gtfs/static/feed"
    ]
    assert registry.search(tags=["offline", "nonexistent"]) == []
    assert registry.tags() == ["gtfs", "offline"]
    assert registry.groups() == ["gtfs/static"]


def test_registry_tree_is_nested(scripts_root: Path):
    tree = ScriptRegistry(scripts_root).tree()
    assert tree["gtfs"]["static"]["feed"].script_id == "gtfs/static/feed"
    assert tree["bare"].script_id == "bare"


def test_registry_refresh_picks_up_new_files(scripts_root: Path):
    registry = ScriptRegistry(scripts_root)
    (scripts_root / "added.py").write_text(BARE_NOTEBOOK)
    assert "added" not in {s.script_id for s in registry.all()}
    registry.refresh()
    assert "added" in {s.script_id for s in registry.all()}


def test_unknown_script_id_raises(scripts_root: Path):
    with pytest.raises(KeyError):
        ScriptRegistry(scripts_root).get("nope")


def test_load_runs_cells_and_returns_independent_apps(scripts_root: Path):
    registry = ScriptRegistry(scripts_root)
    app = registry.load("gtfs/static/feed")
    _outputs, defs = app.run()
    assert defs["doubled"] == 42
    assert registry.load("gtfs/static/feed") is not app


def test_load_app_from_path_on_real_repo_script():
    root = Path(__file__).resolve().parents[1] / "scripts"
    app = load_app_from_path(root / "benchmark" / "eta_accuracy_demo.py")
    assert app is not None
