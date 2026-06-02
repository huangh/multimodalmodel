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

## Running the app

### After installing with uv sync

```bash
uv run marimo run app.py       # read-only interactive view
uv run marimo edit app.py      # editable notebook
```

### After pip install (script entry points)

```bash
multimodalmodel-app            # launches `marimo run app.py`
multimodalmodel                # prints usage info
```

### Without installing

```bash
uv run marimo run app.py
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

## Development

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format .
```
