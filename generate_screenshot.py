"""Generate a static screenshot of the IBI benchmark chart for the repository."""

import os
import random

import plotly.graph_objects as go
import polars as pl

BIN_SPECS = [
    {"label": "0-3 min", "min_s": 0, "max_s": 180, "early_s": 30, "late_s": 90},
    {"label": "3-6 min", "min_s": 180, "max_s": 360, "early_s": 60, "late_s": 150},
    {"label": "6-10 min", "min_s": 360, "max_s": 600, "early_s": 60, "late_s": 210},
    {"label": "10-15 min", "min_s": 600, "max_s": 900, "early_s": 90, "late_s": 270},
]

rng = random.Random(42)
rows = []
for _ in range(200):
    spec = rng.choice(BIN_SPECS)
    predicted = rng.uniform(spec["min_s"], spec["max_s"])
    error = rng.gauss(15, 55)
    actual = max(0.0, predicted + error)
    rows.append({"predicted_s": round(predicted, 1), "actual_s": round(actual, 1)})

df = pl.DataFrame(rows)

bin_expr = (
    pl.when(pl.col("predicted_s").is_between(0, 180, closed="left"))
    .then(pl.lit("0-3 min"))
    .when(pl.col("predicted_s").is_between(180, 360, closed="left"))
    .then(pl.lit("3-6 min"))
    .when(pl.col("predicted_s").is_between(360, 600, closed="left"))
    .then(pl.lit("6-10 min"))
    .when(pl.col("predicted_s").is_between(600, 900, closed="left"))
    .then(pl.lit("10-15 min"))
    .otherwise(pl.lit(None, dtype=pl.String))
)

df = df.with_columns(
    [
        bin_expr.alias("bin"),
        (pl.col("actual_s") - pl.col("predicted_s")).alias("error_s"),
    ]
)

specs_df = pl.DataFrame(BIN_SPECS).rename({"label": "bin"})
df = df.join(specs_df, on="bin", how="left").with_columns(
    (
        (pl.col("error_s") >= -pl.col("early_s"))
        & (pl.col("error_s") <= pl.col("late_s"))
    ).alias("is_accurate")
)

bin_order = [s["label"] for s in BIN_SPECS]
agg = (
    df.filter(pl.col("bin").is_not_null())
    .group_by("bin")
    .agg(
        [
            pl.col("is_accurate").sum().alias("accurate_n"),
            pl.len().alias("total_n"),
        ]
    )
    .with_columns(
        (pl.col("accurate_n") / pl.col("total_n") * 100).round(1).alias("accuracy_pct")
    )
)

all_bins = pl.DataFrame({"bin": bin_order})
results_df = all_bins.join(agg, on="bin", how="left").with_columns(
    [
        pl.col("accurate_n").fill_null(0),
        pl.col("total_n").fill_null(0),
        pl.col("accuracy_pct").fill_null(0.0),
    ]
)
overall_accuracy = float(results_df["accuracy_pct"].mean())

print(results_df)
print(f"Overall accuracy: {overall_accuracy:.1f}%")

colors = [
    "#2ecc71" if v >= 90 else "#f39c12" if v >= 80 else "#e74c3c"
    for v in results_df["accuracy_pct"].to_list()
]

fig = go.Figure()
fig.add_trace(
    go.Bar(
        x=results_df["bin"].to_list(),
        y=results_df["accuracy_pct"].to_list(),
        name="Accuracy %",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in results_df["accuracy_pct"].to_list()],
        textposition="outside",
    )
)

fig.add_hline(
    y=90,
    line_dash="dash",
    line_color="green",
    annotation_text="90% - Great",
    annotation_position="right",
)
fig.add_hline(
    y=80,
    line_dash="dot",
    line_color="orange",
    annotation_text="80% - Good",
    annotation_position="right",
)
fig.add_hline(
    y=overall_accuracy,
    line_dash="solid",
    line_color="#3498db",
    line_width=2,
    annotation_text=f"Overall: {overall_accuracy:.1f}%",
    annotation_position="left",
)

fig.update_layout(
    title="IBI/TransitApp ETA Accuracy Benchmark",
    xaxis_title="Prediction Horizon Bin",
    yaxis_title="Accuracy (%)",
    yaxis={"range": [0, 115]},
    template="plotly_white",
    height=480,
    width=800,
    showlegend=False,
)

os.makedirs("screenshots", exist_ok=True)
fig.write_image("screenshots/benchmark.png", scale=2)
print("Screenshot saved to screenshots/benchmark.png")
