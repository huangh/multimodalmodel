"""multimodalmodel — IBI/TransitApp ETA accuracy benchmark toolkit."""

from multimodalmodel.benchmark import (
    BIN_SPECS,
    classify_predictions,
    compute_accuracy,
    generate_sample_data,
)
from multimodalmodel.charts import make_benchmark_chart

__all__ = [
    "BIN_SPECS",
    "classify_predictions",
    "compute_accuracy",
    "generate_sample_data",
    "make_benchmark_chart",
]


def main() -> None:
    print("multimodalmodel — IBI ETA Accuracy Benchmark")
    print("Run `marimo run app.py` to launch the interactive app.")
    print("Or use `multimodalmodel-app` if installed via pip/uv.")


def run_app() -> None:
    """Launch the Marimo interactive app."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent.parent / "app.py"
    sys.exit(subprocess.call(["marimo", "run", str(app_path)]))
