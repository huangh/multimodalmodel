"""Generate a static benchmark chart screenshot with realistic MBTA Red Line data.

Prediction horizons use real MBTA Red Line geometry (stop spacing / dwell times).
Prediction errors are simulated with a realistic Gaussian distribution matching
typical MBTA accuracy (μ ≈ +12 s late, σ ≈ 55 s).

Run:  uv run python generate_mbta_screenshot.py
Output: screenshots/mbta_benchmark.png
"""

import os
import random
import time
from datetime import datetime

import polars as pl

from multimodalmodel.benchmark import classify_predictions, compute_accuracy
from multimodalmodel.charts import make_benchmark_chart

# ── Red Line southbound geometry (real MBTA stop IDs) ─────────────────────────
_RL_STOPS = [
    ("70061", "Alewife"),
    ("70063", "Davis"),
    ("70065", "Porter"),
    ("70067", "Harvard"),
    ("70069", "Central"),
    ("70071", "Kendall/MIT"),
    ("70073", "Charles/MGH"),
    ("70075", "Park St"),
    ("70077", "Downtown Crossing"),
    ("70079", "South Station"),
    ("70081", "Broadway"),
    ("70083", "Andrew"),
    ("70085", "JFK/UMass"),
    ("70087", "Savin Hill"),
    ("70089", "Fields Corner"),
    ("70091", "Shawmut"),
    ("70093", "Ashmont"),
]
_RL_SEG_S = [120, 90, 90, 120, 90, 120, 150, 90, 90, 120, 90, 120, 150, 90, 90, 90]


def _simulate_mbta_pairs(n_trains: int = 10, seed: int = 42) -> pl.DataFrame:
    """Return (predicted_s, actual_s) pairs from simulated Red Line trains.

    - predicted_s: time-to-arrival as seen in the API snapshot
    - actual_s:    simulated actual arrival time (predicted + realistic noise)
    """
    rng = random.Random(seed)
    now = time.time()
    headway_s = 390
    rows: list[dict] = []

    for i in range(n_trains):
        offset = i * headway_s + rng.gauss(0, 25)
        if offset < 0:
            offset = 0

        cumulative = 0.0
        seg_idx = 0
        for j, seg in enumerate(_RL_SEG_S):
            if cumulative + seg > offset:
                seg_idx = j
                break
            cumulative += seg
        else:
            continue

        time_to_next = (cumulative + _RL_SEG_S[seg_idx]) - offset
        running_s = time_to_next

        for seq in range(seg_idx, len(_RL_STOPS)):
            if running_s > 920:
                break
            predicted_s = running_s + rng.gauss(5, 12)
            if predicted_s <= 0:
                if seq < len(_RL_SEG_S):
                    running_s += _RL_SEG_S[seq] + rng.gauss(4, 10)
                continue

            # MBTA is generally accurate; simulate realistic error
            error_s = rng.gauss(12, 52)
            actual_s = max(0.0, predicted_s + error_s)
            rows.append({"predicted_s": float(predicted_s), "actual_s": float(actual_s)})

            if seq < len(_RL_SEG_S):
                running_s += _RL_SEG_S[seq] + rng.gauss(4, 10)

    return pl.DataFrame(rows) if rows else pl.DataFrame(
        {"predicted_s": pl.Series([], dtype=pl.Float64),
         "actual_s": pl.Series([], dtype=pl.Float64)}
    )


print("Simulating MBTA Red Line prediction data ...")
df = _simulate_mbta_pairs(n_trains=10, seed=42)
print(f"  {len(df)} (predicted_s, actual_s) pairs generated")

classified = classify_predictions(df)
predictions_df = classified.filter(classified["bin"].is_not_null())
results_df, overall = compute_accuracy(classified)

print(f"\nIBI accuracy summary (simulated):")
for row in results_df.iter_rows(named=True):
    bar = "█" * int(row["accuracy_pct"] / 5)
    print(f"  {row['bin']:12}  {row['accuracy_pct']:5.1f}%  {bar}")
print(f"  {'Overall':12}  {overall:5.1f}%")

fig = make_benchmark_chart(predictions_df)
fig.update_layout(
    title=(
        f"MBTA Red Line — IBI ETA Accuracy  "
        f"({datetime.now().strftime('%Y-%m-%d %H:%M')})<br>"
        f"<sup>{len(predictions_df)} predictions in IBI range · Overall {overall:.1f}% accurate"
        f" · Simulated (real stop geometry, Gaussian error σ≈55 s)</sup>"
    ),
    width=1040,
    height=580,
)

os.makedirs("screenshots", exist_ok=True)
out_path = "screenshots/mbta_benchmark.png"
fig.write_image(out_path, scale=2)
print(f"\nScreenshot saved → {out_path}")
