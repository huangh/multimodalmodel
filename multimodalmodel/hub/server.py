"""ASGI server that hosts the hub notebook plus a JSON usage API.

Layout:

===========================  =================================================
``/``                        the hub notebook (dropdown + dynamically embedded
                             script), one marimo kernel per browser session
``/s/<script_id>``           any script served standalone, for sharing a link
                             straight to one plot
``/api/scripts``             registry listing (JSON)
``/api/usage/top``           most-used scripts (JSON)
``/api/usage/recent``        recent usage events (JSON)
``/healthz``                 liveness probe
===========================  =================================================

Run it with ``multimodalmodel-hub`` or ``python -m multimodalmodel.hub.server``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from multimodalmodel.hub import default_scripts_root
from multimodalmodel.hub.registry import ScriptRegistry
from multimodalmodel.hub.usage import UsageStore, default_db_path

HUB_NOTEBOOK_ENV = "MBTA_HUB_NOTEBOOK"


def default_hub_notebook() -> Path:
    env = os.environ.get(HUB_NOTEBOOK_ENV)
    if env:
        return Path(env).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "notebooks" / "hub.py"
        if candidate.is_file():
            return candidate
    return Path("notebooks/hub.py").resolve()


def _script_meta_json(meta: Any) -> dict[str, Any]:
    return {
        "script_id": meta.script_id,
        "title": meta.title,
        "description": meta.description,
        "group": meta.group,
        "tags": list(meta.tags),
        "params": list(meta.params),
        "path": str(meta.path),
        "url": f"/s/{meta.script_id}",
        "error": meta.error,
    }


def create_app(
    *,
    scripts_root: Path | None = None,
    hub_notebook: Path | None = None,
    db_path: Path | None = None,
    include_code: bool = True,
    mount_scripts: bool = True,
) -> Any:
    """Build the Starlette app hosting the hub, the scripts, and the API."""
    import marimo
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, RedirectResponse
    from starlette.routing import Mount, Route

    scripts_root = Path(scripts_root or default_scripts_root()).resolve()
    hub_notebook = Path(hub_notebook or default_hub_notebook()).resolve()
    store = UsageStore(db_path or default_db_path())
    registry = ScriptRegistry(scripts_root)

    # Child kernels read these to find the same tree and database as the server.
    os.environ.setdefault("MBTA_HUB_SCRIPTS", str(scripts_root))
    os.environ.setdefault("MBTA_HUB_USAGE_DB", str(store.db_path))

    builder = marimo.create_asgi_app(include_code=include_code)
    builder = builder.with_app(path="/", root=str(hub_notebook))
    mounted: list[str] = []
    if mount_scripts:
        for meta in registry.all():
            if meta.error is None:
                builder = builder.with_app(
                    path=f"/s/{meta.script_id}", root=str(meta.path)
                )
                mounted.append(meta.script_id)
    marimo_app = builder.build()

    def _slash_redirect(script_id: str) -> Route:
        # Nested marimo mounts only answer on the trailing-slash form; redirect
        # the bare path so /s/<script_id> links work. Exact paths only, so the
        # mounted app keeps serving its own assets underneath.
        async def _redirect(request: Any) -> RedirectResponse:
            return RedirectResponse(f"/s/{script_id}/")

        return Route(f"/s/{script_id}", _redirect)

    async def list_scripts(request: Any) -> JSONResponse:
        query = request.query_params.get("q", "")
        tags = [t for t in request.query_params.get("tags", "").split(",") if t]
        registry.refresh()
        counts = store.counts()
        scripts = registry.search(query, tags)
        return JSONResponse(
            {
                "scripts_root": str(scripts_root),
                "count": len(scripts),
                "scripts": [
                    {**_script_meta_json(m), "uses": counts.get(m.script_id, 0)}
                    for m in scripts
                ],
            }
        )

    async def usage_top(request: Any) -> JSONResponse:
        limit = int(request.query_params.get("limit", 10))
        since = request.query_params.get("since_days")
        rows = store.top(limit, since_days=float(since) if since else None)
        return JSONResponse(
            [
                {
                    "script_id": u.script_id,
                    "uses": u.uses,
                    "unique_users": u.unique_users,
                    "last_used": u.last_used,
                    "errors": u.errors,
                }
                for u in rows
            ]
        )

    async def usage_recent(request: Any) -> JSONResponse:
        limit = int(request.query_params.get("limit", 25))
        return JSONResponse(store.recent(limit))

    async def healthz(request: Any) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "scripts": len(registry.all()),
                "usage_events": store.total_events(),
            }
        )

    return Starlette(
        routes=[
            Route("/healthz", healthz),
            Route("/api/scripts", list_scripts),
            Route("/api/usage/top", usage_top),
            Route("/api/usage/recent", usage_recent),
            *[_slash_redirect(script_id) for script_id in mounted],
            Mount("/", app=marimo_app),
        ]
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the MBTA script hub")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--scripts-root", type=Path, default=None)
    parser.add_argument("--notebook", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument(
        "--no-script-mounts",
        action="store_true",
        help="Do not serve each script standalone under /s/<script_id>",
    )
    args = parser.parse_args(argv)

    import uvicorn

    app = create_app(
        scripts_root=args.scripts_root,
        hub_notebook=args.notebook,
        db_path=args.db,
        mount_scripts=not args.no_script_mounts,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
