---
title: marimo app template
emoji: 🍃
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: true
license: mit
short_description: Template for deploying a marimo application to HF
---
Check out marimo at <https://github.com/marimo-team/marimo>
Check out the configuration reference at <https://huggingface.co/docs/hub/spaces-config-reference>

# multimodalmodel

IBI/TransitApp ETA accuracy benchmark for transit prediction evaluation.

## Installation

### With uv (recommended)

```bash
# Install into a managed virtual environment
uv sync

# Or install directly (editable)
uv pip install -e .
```

### With pip

```bash
pip install .

# Editable / development install
pip install -e .
```

## Running the apps

### Synthetic demo (`app.py`)

```bash
uv run marimo run app.py       # read-only interactive view
uv run marimo edit app.py      # editable notebook
multimodalmodel-app            # entry point (after pip/uv install)
```

### Live GTFS-RT app (`live_app.py`)

```bash
uv run marimo run live_app.py
multimodalmodel-live           # entry point (after pip/uv install)
```

The live app polls real GTFS-RT feeds and plots prediction accuracy as vehicles
arrive at stops.

**Configuration fields in the UI:**

| Field | Description |
|---|---|
| GTFS-RT URL | Required. Used for both trip updates and vehicle positions by default. |
| Vehicle positions URL override | Optional. Provide a separate URL if your agency publishes vehicle positions on a different endpoint. |
| API key | Optional. Sent as `X-API-Key` header. |
| Poll interval | How often to re-fetch (10 s – 60 s). |
| Live polling switch | Toggle to start/stop polling. |

**Preview mode**: while fewer than 10 verified arrivals have accumulated the
chart shows a proxy view built from the current `arrival_delay` field in trip
updates. A blue callout indicates preview mode; it disappears automatically
once enough real arrival events are detected.

**Public GTFS-RT feeds to try** (no API key required):

```
# MTA New York City Transit — subway trip updates
https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs

# Bay Area 511 (requires free API key at https://511.org/open-data/token)
# Trip updates:
https://api.511.org/transit/tripupdates?agency=SF&api_key=YOUR_KEY
# Vehicle positions:
https://api.511.org/transit/vehiclepositions?agency=SF&api_key=YOUR_KEY
```

## Using as a library

After installation the core logic is importable:

```python
from multimodalmodel import (
    BIN_SPECS,
    generate_sample_data,
    classify_predictions,
    compute_accuracy,
    make_benchmark_chart,
)

df = generate_sample_data(n=500, seed=0)
classified = classify_predictions(df)
results, overall_pct = compute_accuracy(classified)
print(f"Overall accuracy: {overall_pct:.1f}%")

# Build a standalone Plotly figure
predictions = classified.filter(classified["bin"].is_not_null())
fig = make_benchmark_chart(predictions)
fig.show()
```

### API

| Symbol | Module | Description |
|---|---|---|
| `BIN_SPECS` | `benchmark` | List of 4 time-horizon bin configs |
| `generate_sample_data(n, seed)` | `benchmark` | Synthetic `(predicted_s, actual_s)` DataFrame |
| `classify_predictions(df)` | `benchmark` | Adds `bin`, `error_s`, `is_accurate` columns |
| `compute_accuracy(classified)` | `benchmark` | Returns `(results_df, overall_pct)` |
| `make_benchmark_chart(predictions_df)` | `charts` | Returns a Plotly `Figure` |
| `fetch_feed(url, headers, timeout)` | `gtfs_rt` | Fetches a GTFS-RT binary feed via HTTP |
| `parse_trip_updates(feed_bytes, snapshot_time)` | `gtfs_rt` | Parses trip update entities → DataFrame |
| `parse_vehicle_positions(feed_bytes, snapshot_time)` | `gtfs_rt` | Parses vehicle position entities → DataFrame |
| `PredictionTracker` | `live_tracker` | Accumulates predictions and resolves arrivals |

## Development

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format .
```
