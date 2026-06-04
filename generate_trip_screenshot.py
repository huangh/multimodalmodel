"""Generate a static trip profile chart screenshot using simulated Red Line data.

One complete southbound Red Line trip (Alewife → Ashmont) running ~2.5 min late.
Per-stop prediction counts are simulated from realistic polling history.

Run:  uv run python generate_trip_screenshot.py
Output: screenshots/trip_profile.png
"""

import os
import random
import time
from datetime import datetime

import polars as pl

from multimodalmodel.benchmark import BIN_SPECS, classify_predictions_by_stop
from multimodalmodel.charts import make_trip_profile_chart

# ── Red Line southbound geometry (real MBTA stop IDs + names) ─────────────────
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


def _simulate_trip_profile(seed: int = 42) -> tuple[pl.DataFrame, float]:
    """Simulate a complete Red Line trip with per-stop prediction histories."""
    rng = random.Random(seed)
    now = time.time()

    # Trip started 38 minutes ago — all stops have passed
    trip_start = now - 38 * 60

    # Scheduled arrival times
    sched_times = [trip_start]
    for seg in _RL_SEG_S:
        sched_times.append(sched_times[-1] + seg)

    # Actual arrivals: train runs ~2.5 min late with slight accumulation
    base_delay_s = 150.0
    actual_times = []
    running_delay = base_delay_s
    for sched in sched_times:
        running_delay += rng.gauss(2, 12)
        actual_times.append(sched + max(0.0, running_delay))

    # Per-stop prediction histories
    rows: list[dict] = []
    for i, (stop_id, stop_name) in enumerate(_RL_STOPS):
        scheduled_min = (sched_times[i] - trip_start) / 60
        actual_min = (actual_times[i] - trip_start) / 60
        delay_s = actual_times[i] - sched_times[i]

        # Simulate polling over the 15 min window before this stop
        n_preds = rng.randint(14, 28)
        correct = 0
        incorrect = 0

        for _ in range(n_preds):
            # Each prediction was made when the stop was predicted_s seconds away
            predicted_s = rng.uniform(20, 890)

            # Error biased toward the actual delay, with realistic noise
            error_s = rng.gauss(delay_s * 0.6, 48)
            actual_s = max(0.0, predicted_s + error_s)

            # IBI classification
            for spec in BIN_SPECS:
                if spec["min_s"] <= predicted_s < spec["max_s"]:
                    err = actual_s - predicted_s
                    if -spec["early_s"] <= err <= spec["late_s"]:
                        correct += 1
                    else:
                        incorrect += 1
                    break

        rows.append({
            "stop_id": stop_id,
            "stop_sequence": i + 1,
            "stop_name": stop_name,
            "scheduled_min": scheduled_min,
            "actual_min": actual_min,
            "correct_count": correct,
            "incorrect_count": incorrect,
        })

    profile_df = pl.DataFrame(rows, schema={
        "stop_id": pl.String,
        "stop_sequence": pl.Int32,
        "stop_name": pl.String,
        "scheduled_min": pl.Float64,
        "actual_min": pl.Float64,
        "correct_count": pl.Int32,
        "incorrect_count": pl.Int32,
    })

    return profile_df, trip_start


print("Simulating MBTA Red Line southbound trip ...")
profile_df, trip_start = _simulate_trip_profile(seed=42)
print(f"  {len(profile_df)} stops")

total_correct = int(profile_df["correct_count"].sum())
total_incorrect = int(profile_df["incorrect_count"].sum())
total = total_correct + total_incorrect
overall_pct = total_correct / total * 100 if total else 0

print(f"\nPer-stop summary:")
print(f"  {'Stop':<20} {'Sched':>6} {'Actual':>6} {'Delay':>6}  {'Acc':>5}")
print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}  {'-'*5}")
for row in profile_df.iter_rows(named=True):
    delay = (row["actual_min"] - row["scheduled_min"]) * 60
    total_stop = row["correct_count"] + row["incorrect_count"]
    pct = row["correct_count"] / total_stop * 100 if total_stop else 0
    print(
        f"  {row['stop_name']:<20} {row['scheduled_min']:>5.1f}m {row['actual_min']:>5.1f}m "
        f" {delay:>+5.0f}s  {pct:>4.0f}%"
    )

print(f"\nOverall IBI accuracy: {overall_pct:.1f}%  ({total_correct}/{total} predictions)")

trip_id = "canonical-60547000-Red-1-Weekday-01"
fig = make_trip_profile_chart(profile_df, trip_id=trip_id)
fig.update_layout(
    title=(
        f"MBTA Red Line (Alewife → Ashmont) — Trip Profile  "
        f"({datetime.now().strftime('%Y-%m-%d %H:%M')})<br>"
        f"<sup>Simulated trip · ~2.5 min delay · {overall_pct:.1f}% IBI accuracy "
        f"({total_correct}/{total} predictions)</sup>"
    ),
    width=1060,
    height=640,
)

os.makedirs("screenshots", exist_ok=True)
out = "screenshots/trip_profile.png"
fig.write_image(out, scale=2)
print(f"\nScreenshot saved → {out}")
