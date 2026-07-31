# Script hub

A marimo front end that lists every analysis script in a nested folder, renders
the one you pick **into the page you are already looking at**, and records what
gets used so the popular plots float to the top.

```
notebooks/hub.py             the front end (a marimo notebook)
scripts/                     the script library, nested however you like
  benchmark/eta_accuracy_demo.py
  gtfs/static/feed_summary.py
  mbta/realtime/vehicle_positions.py
  mbta/realtime/prediction_horizons.py
  _template.py               starts with _, so the registry skips it
multimodalmodel/hub/
  registry.py                discovery + metadata + dynamic loading
  usage.py                   SQLite usage log
  server.py                  ASGI app: hub + per-script pages + JSON API
```

## Run it

```bash
uv run multimodalmodel-hub --port 8000          # server (hub + /s/<id> + API)
uv run marimo run notebooks/hub.py              # hub notebook only
uv run marimo edit scripts/gtfs/static/feed_summary.py   # edit one script
```

Open `http://localhost:8000/?user=alice` — the `user` query parameter is how a
viewer identifies themselves, and it lands in the usage log.

| Env var | Meaning | Default |
|---|---|---|
| `MBTA_HUB_SCRIPTS` | scripts root | nearest `scripts/` above the package |
| `MBTA_HUB_USAGE_DB` | usage database | `.hub/usage.db` |
| `MBTA_HUB_NOTEBOOK` | hub notebook path | nearest `notebooks/hub.py` |

## How dynamic rendering works

marimo's dataflow graph is static per notebook, so the hub does not splice
cells into its own graph. It uses `App.embed()` instead — the supported way to
run one notebook inside another:

```python
script_app = registry.load(selected_id)   # one cell: load the file
result = await script_app.embed()         # another cell: run it
result.output                             # a third: show it
```

`embed()` runs the loaded notebook in its own kernel runner and returns its
rendered output plus its variables. Widgets inside the embedded script stay
live: interacting with them re-runs the embedded notebook, and any hub cell
referring to the app object is marked stale. `embed(defs={...})` overrides
variables in the embedded notebook, which is how the hub can pass shared
context (an API key, a feed path) into a script — declare those names under
`params` in the script's frontmatter.

Two constraints worth knowing:

* `embed()` cannot be called in the cell that defines/imports the app — hence
  the load/embed/display split above.
* Each `registry.load()` returns a fresh `App`, so two viewers (and two
  selections) never share cell state.

## Adding a script

Copy `scripts/_template.py`, drop it anywhere under `scripts/`, and press
**Rescan scripts**. Metadata lives in a comment block that marimo preserves and
that the registry reads *without importing the file*:

```python
# /// hub
# title = "Route stop counts"
# description = "Stops per route from a static GTFS feed."
# tags = ["gtfs", "static"]
# params = ["gtfs_dir"]
# ///
```

Every field is optional; the title falls back to `marimo.App(app_title=...)`,
then the module docstring, then a humanized filename. Files beginning with `_`
and anything under `__pycache__` are skipped. A script with a syntax error is
still listed, marked ⚠️, with the error shown rather than swallowed.

Keep the initial render cheap — put anything that hits the network behind a
`mo.ui.run_button` so opening a script does not fire requests.

## Usage tracking

Every render writes a row to `usage_events` (script, user, session, timestamp,
duration, error). Reads power the dropdown ordering (most-used first, with a
`· N×` suffix), the leaderboard, and `/api/usage/*`.

Repeat renders from the same session within 30 s collapse into one event.
That matters because marimo re-runs the embed chain whenever a widget inside
the embedded script changes — without the window, dragging a slider would look
like heavy usage.

SQLite in WAL mode with short-lived connections is deliberate: marimo spawns
one kernel process per viewer, and they all write to the same file.

## HTTP surface

| Route | What |
|---|---|
| `/` | the hub |
| `/s/<script_id>` | one script served standalone (shareable link) |
| `/api/scripts?q=&tags=` | registry listing with usage counts |
| `/api/usage/top?limit=&since_days=` | leaderboard data |
| `/api/usage/recent?limit=` | raw event tail |
| `/healthz` | liveness |

## Prototype limits

* The registry scans on kernel start and on **Rescan scripts**; there is no
  file watcher yet.
* `user` comes from a query parameter — fine behind an authenticating proxy,
  not an identity system.
* Every script mounted at `/s/<id>` is registered at server start, so new
  scripts need a restart to get their standalone URL (they show up in the hub
  dropdown immediately).
* Scripts execute in the server's process with no sandbox. Treat the scripts
  directory as trusted code — the same trust level as the server itself.
