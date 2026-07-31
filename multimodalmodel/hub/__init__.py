"""Script hub: a marimo front end that renders a library of analysis scripts.

The hub is one notebook (``notebooks/hub.py``) that lists every marimo script
found under a scripts root, lets a viewer pick one from a dropdown, embeds it
into the current page, and logs the selection so popular scripts can be
surfaced first.
"""

from __future__ import annotations

import os
from pathlib import Path

from multimodalmodel.hub.registry import (
    ScriptLoadError,
    ScriptMeta,
    ScriptRegistry,
    discover_scripts,
    load_app_from_path,
)
from multimodalmodel.hub.usage import ScriptUsage, UsageStore, default_db_path

SCRIPTS_ROOT_ENV = "MBTA_HUB_SCRIPTS"


def default_scripts_root() -> Path:
    """Where hub scripts live.

    ``MBTA_HUB_SCRIPTS`` wins; otherwise walk up from this file looking for a
    ``scripts`` directory (works from a source checkout), and fall back to
    ``./scripts`` relative to the process working directory.
    """
    env = os.environ.get(SCRIPTS_ROOT_ENV)
    if env:
        return Path(env).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts"
        if candidate.is_dir():
            return candidate
    return Path("scripts").resolve()


__all__ = [
    "SCRIPTS_ROOT_ENV",
    "ScriptLoadError",
    "ScriptMeta",
    "ScriptRegistry",
    "ScriptUsage",
    "UsageStore",
    "default_db_path",
    "default_scripts_root",
    "discover_scripts",
    "load_app_from_path",
]
