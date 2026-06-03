"""multimodalmodel — IBI/TransitApp ETA accuracy benchmark toolkit."""

from multimodalmodel.benchmark import (
    BIN_SPECS,
    classify_predictions,
    classify_predictions_by_stop,
    compute_accuracy,
    generate_sample_data,
)
from multimodalmodel.charts import make_benchmark_chart, make_trip_profile_chart
from multimodalmodel.gtfs_rt import fetch_feed, parse_trip_updates, parse_vehicle_positions
from multimodalmodel.live_tracker import (
    MIN_RESOLVED_FOR_CHART,
    PredictionTracker,
    build_trip_profile_df,
)
from multimodalmodel.mbta import (
    MBTA_SUBWAY_ROUTES,
    fetch_mbta_predictions,
    fetch_mbta_vehicles,
)

__all__ = [
    "BIN_SPECS",
    "MBTA_SUBWAY_ROUTES",
    "MIN_RESOLVED_FOR_CHART",
    "PredictionTracker",
    "build_trip_profile_df",
    "classify_predictions",
    "classify_predictions_by_stop",
    "compute_accuracy",
    "fetch_feed",
    "fetch_mbta_predictions",
    "fetch_mbta_vehicles",
    "generate_sample_data",
    "make_benchmark_chart",
    "make_trip_profile_chart",
    "parse_trip_updates",
    "parse_vehicle_positions",
]


def main() -> None:
    print("multimodalmodel — IBI ETA Accuracy Benchmark")
    print("  marimo run app.py          — synthetic demo")
    print("  marimo run live_app.py     — live GTFS-RT feed")
    print("  marimo run mbta_app.py     — live MBTA v3 API feed")
    print("  multimodalmodel-app        — launch demo (installed entry point)")
    print("  multimodalmodel-live       — launch live GTFS-RT app")
    print("  multimodalmodel-mbta       — launch MBTA v3 live app")


def run_app() -> None:
    """Launch the synthetic demo Marimo app."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent.parent / "app.py"
    sys.exit(subprocess.call(["marimo", "run", str(app_path)]))


def run_live_app() -> None:
    """Launch the live GTFS-RT Marimo app."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent.parent / "live_app.py"
    sys.exit(subprocess.call(["marimo", "run", str(app_path)]))


def run_mbta_app() -> None:
    """Launch the MBTA v3 live Marimo app."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent.parent / "mbta_app.py"
    sys.exit(subprocess.call(["marimo", "run", str(app_path)]))
