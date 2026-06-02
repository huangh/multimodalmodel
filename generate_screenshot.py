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

predictions_df = df.filter(pl.col("bin").is_not_null())
print(f"Predictions in range: {len(predictions_df)}")

# Convert to minutes
pm = predictions_df["predicted_s"] / 60
em = predictions_df["error_s"] / 60
accurate = predictions_df["is_accurate"]
too_late = ~accurate & (em > predictions_df["late_s"] / 60)
too_early = ~accurate & (em < -(predictions_df["early_s"] / 60))


def fmt(seconds: int, positive: bool) -> str:
    m, s = abs(seconds) // 60, abs(seconds) % 60
    sign = "+" if positive else "-"
    if m and s:
        return f"{sign}{m}m {s}s"
    return f"{sign}{m}m" if m else f"{sign}{s}s"


# Staircase coordinates in minutes (x-axis reversed: 15 → 0)
xs = [15.0, 10.0, 10.0, 6.0, 6.0, 3.0, 3.0, 0.0]
y_up = [4.5, 4.5, 3.5, 3.5, 2.5, 2.5, 1.5, 1.5]
y_lo = [-1.5, -1.5, -1.0, -1.0, -1.0, -1.0, -0.5, -0.5]

fig = go.Figure()

# Green fill between staircases
fig.add_trace(
    go.Scatter(
        x=xs,
        y=y_lo,
        mode="lines",
        line=dict(color="rgba(0,168,89,0.75)", width=2),
        fill=None,
        showlegend=False,
        hoverinfo="skip",
    )
)
fig.add_trace(
    go.Scatter(
        x=xs,
        y=y_up,
        mode="lines",
        line=dict(color="rgba(0,168,89,0.75)", width=2),
        fill="tonexty",
        fillcolor="rgba(46,204,113,0.18)",
        showlegend=False,
        hoverinfo="skip",
    )
)

# Too late — yellow
xl, yl = pm.filter(too_late).to_list(), em.filter(too_late).to_list()
if xl:
    fig.add_trace(
        go.Scatter(
            x=xl,
            y=yl,
            mode="markers",
            marker=dict(color="#f1c40f", size=9, line=dict(color="white", width=1)),
            name="Excess wait time — Inaccurate ETA",
        )
    )

# Accurate — green
xa, ya = pm.filter(accurate).to_list(), em.filter(accurate).to_list()
if xa:
    fig.add_trace(
        go.Scatter(
            x=xa,
            y=ya,
            mode="markers",
            marker=dict(color="#2ecc71", size=9, line=dict(color="white", width=1)),
            name="Catch the ride — Accurate ETA",
        )
    )

# Too early — pink
xe, ye = pm.filter(too_early).to_list(), em.filter(too_early).to_list()
if xe:
    fig.add_trace(
        go.Scatter(
            x=xe,
            y=ye,
            mode="markers",
            marker=dict(color="#e91e63", size=9, line=dict(color="white", width=1)),
            name="Miss the ride — Inaccurate ETA",
        )
    )

# Bin separators
for bx in [3.0, 6.0, 10.0]:
    fig.add_vline(x=bx, line_dash="dot", line_color="#cccccc", line_width=1.5)

# Arrival line
fig.add_vline(x=0.0, line_color="#2196f3", line_width=2.5)
fig.add_annotation(
    x=0.0,
    y=1.0,
    xref="x",
    yref="paper",
    text="<b>ARRIVAL</b>",
    font=dict(color="#2196f3", size=11),
    showarrow=False,
    xanchor="left",
    yanchor="bottom",
)

cat_labels = [
    "Where is my ride?",
    "Do I need to hustle?",
    "Do I need to leave now?",
    "Is the vehicle coming?",
]
for i, spec in enumerate(BIN_SPECS):
    xmid = (spec["min_s"] + spec["max_s"]) / 2 / 60
    fig.add_annotation(
        x=xmid,
        y=spec["late_s"] / 60 + 0.18,
        text=fmt(spec["late_s"], positive=True),
        showarrow=False,
        font=dict(size=10, color="#444"),
        yanchor="bottom",
    )
    fig.add_annotation(
        x=xmid,
        y=-spec["early_s"] / 60 - 0.18,
        text=fmt(spec["early_s"], positive=False),
        showarrow=False,
        font=dict(size=10, color="#444"),
        yanchor="top",
    )
    fig.add_annotation(
        x=xmid,
        y=1.04,
        xref="x",
        yref="paper",
        text=f"<i>{cat_labels[i]}</i>",
        showarrow=False,
        font=dict(size=11, color="#777"),
        yanchor="bottom",
    )
    fig.add_annotation(
        x=xmid,
        y=-0.08,
        xref="x",
        yref="paper",
        text=f"{spec['label']} away",
        showarrow=False,
        font=dict(size=11, color="#444"),
        yanchor="top",
    )

fig.update_layout(
    title="IBI/TransitApp ETA Accuracy Benchmark",
    xaxis=dict(
        title="Time until arrival (minutes)",
        range=[16.0, -0.5],
        tickvals=[0, 3, 6, 10, 15],
        showgrid=False,
        zeroline=False,
    ),
    yaxis=dict(
        title="Prediction error (minutes)",
        range=[-2.2, 5.6],
        zeroline=True,
        zerolinecolor="rgba(180,180,180,0.9)",
        zerolinewidth=1,
        gridcolor="rgba(200,200,200,0.3)",
    ),
    legend=dict(
        orientation="v",
        x=1.01,
        y=0.5,
        xanchor="left",
        bordercolor="#dddddd",
        borderwidth=1,
    ),
    template="plotly_white",
    height=540,
    width=960,
    margin=dict(r=240, t=80, b=80),
)

os.makedirs("screenshots", exist_ok=True)
fig.write_image("screenshots/benchmark.png", scale=2)
print("Screenshot saved to screenshots/benchmark.png")
