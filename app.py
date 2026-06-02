import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # IBI ETA Accuracy Benchmark

    Visualises transit prediction accuracy using the industry-standard **IBI/TransitApp**
    methodology. Each prediction is classified as *accurate* if the vehicle arrived within
    an asymmetric early/late tolerance window that narrows as the bus gets closer.

    **Overall accuracy** is the straight (unweighted) average of the four per-bin accuracy
    percentages, giving equal weight to each horizon bucket.
    """)
    return


@app.cell
def _():
    import plotly.graph_objects as go
    import polars as pl

    return go, pl


@app.cell
def _():
    BIN_SPECS = [
        {
            "label": "0-3 min",
            "min_s": 0,
            "max_s": 180,
            "early_s": 30,
            "late_s": 90,
        },
        {
            "label": "3-6 min",
            "min_s": 180,
            "max_s": 360,
            "early_s": 60,
            "late_s": 150,
        },
        {
            "label": "6-10 min",
            "min_s": 360,
            "max_s": 600,
            "early_s": 60,
            "late_s": 210,
        },
        {
            "label": "10-15 min",
            "min_s": 600,
            "max_s": 900,
            "early_s": 90,
            "late_s": 270,
        },
    ]
    return (BIN_SPECS,)


@app.cell
def _(mo):
    n_predictions = mo.ui.slider(
        start=50,
        stop=500,
        step=50,
        value=200,
        label="Number of synthetic predictions",
    )
    seed = mo.ui.number(start=0, stop=99, step=1, value=42, label="Random seed")
    mo.hstack([n_predictions, seed], justify="start")
    return n_predictions, seed


@app.cell
def _(BIN_SPECS, n_predictions, pl, seed):
    import random

    _rng = random.Random(int(seed.value))
    _rows = []
    for _i in range(int(n_predictions.value)):
        _spec = _rng.choice(BIN_SPECS)
        _predicted = _rng.uniform(_spec["min_s"], _spec["max_s"])
        _error = _rng.gauss(15, 55)
        _actual = max(0.0, _predicted + _error)
        _rows.append(
            {"predicted_s": round(_predicted, 1), "actual_s": round(_actual, 1)}
        )
    sample_df = pl.DataFrame(_rows)
    return (sample_df,)


@app.cell
def _(mo, sample_df):
    editor = mo.ui.data_editor(
        data=sample_df.to_dicts(),
        label="Prediction data — edit or paste your own rows (predicted_s, actual_s in seconds)",
    )
    editor
    return (editor,)


@app.cell
def _(BIN_SPECS, editor, pl):
    _df = pl.DataFrame(editor.value)

    _bin_expr = (
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

    _df = _df.with_columns(
        [
            _bin_expr.alias("bin"),
            (pl.col("actual_s") - pl.col("predicted_s")).alias("error_s"),
        ]
    )

    _specs_df = pl.DataFrame(BIN_SPECS).rename({"label": "bin"})
    _df = _df.join(_specs_df, on="bin", how="left").with_columns(
        (
            (pl.col("error_s") >= -pl.col("early_s"))
            & (pl.col("error_s") <= pl.col("late_s"))
        ).alias("is_accurate")
    )

    _bin_order = [s["label"] for s in BIN_SPECS]
    _agg = (
        _df.filter(pl.col("bin").is_not_null())
        .group_by("bin")
        .agg(
            [
                pl.col("is_accurate").sum().alias("accurate_n"),
                pl.len().alias("total_n"),
            ]
        )
        .with_columns(
            (pl.col("accurate_n") / pl.col("total_n") * 100)
            .round(1)
            .alias("accuracy_pct")
        )
    )

    _all_bins = pl.DataFrame({"bin": _bin_order})
    results_df = _all_bins.join(_agg, on="bin", how="left").with_columns(
        [
            pl.col("accurate_n").fill_null(0),
            pl.col("total_n").fill_null(0),
            pl.col("accuracy_pct").fill_null(0.0),
        ]
    )
    overall_accuracy = float(results_df["accuracy_pct"].mean())
    return overall_accuracy, results_df


@app.cell(hide_code=True)
def _(mo, overall_accuracy, results_df):
    _caption = (
        "Great (≥90%)"
        if overall_accuracy >= 90
        else "Good (≥80%)"
        if overall_accuracy >= 80
        else "Needs improvement"
    )
    mo.hstack(
        [
            mo.stat(
                value=f"{overall_accuracy:.1f}%",
                label="Overall IBI Accuracy",
                caption=_caption,
                bordered=True,
            ),
            mo.stat(
                value=str(int(results_df["total_n"].sum())),
                label="Total Predictions",
                bordered=True,
            ),
            mo.stat(
                value=str(int(results_df["accurate_n"].sum())),
                label="Accurate Predictions",
                bordered=True,
            ),
        ],
        justify="start",
    )
    return


@app.cell
def _(go, mo, overall_accuracy, results_df):
    _colors = [
        "#2ecc71" if v >= 90 else "#f39c12" if v >= 80 else "#e74c3c"
        for v in results_df["accuracy_pct"].to_list()
    ]

    _fig = go.Figure()
    _fig.add_trace(
        go.Bar(
            x=results_df["bin"].to_list(),
            y=results_df["accuracy_pct"].to_list(),
            name="Accuracy %",
            marker_color=_colors,
            text=[f"{v:.1f}%" for v in results_df["accuracy_pct"].to_list()],
            textposition="outside",
        )
    )

    _fig.add_hline(
        y=90,
        line_dash="dash",
        line_color="green",
        annotation_text="90% — Great",
        annotation_position="right",
    )
    _fig.add_hline(
        y=80,
        line_dash="dot",
        line_color="orange",
        annotation_text="80% — Good",
        annotation_position="right",
    )
    _fig.add_hline(
        y=overall_accuracy,
        line_dash="solid",
        line_color="#3498db",
        line_width=2,
        annotation_text=f"Overall: {overall_accuracy:.1f}%",
        annotation_position="left",
    )

    _fig.update_layout(
        title="IBI/TransitApp ETA Accuracy Benchmark",
        xaxis_title="Prediction Horizon Bin",
        yaxis_title="Accuracy (%)",
        yaxis={"range": [0, 115]},
        template="plotly_white",
        height=480,
        showlegend=False,
    )

    mo.ui.plotly(_fig)
    return


@app.cell(hide_code=True)
def _(BIN_SPECS, mo, pl):
    _ref = pl.DataFrame(
        [
            {
                "Bin": s["label"],
                "Early tolerance": (
                    f"-{s['early_s'] // 60}m {s['early_s'] % 60}s"
                    if s["early_s"] % 60
                    else f"-{s['early_s'] // 60}m"
                ),
                "Late tolerance": (
                    f"+{s['late_s'] // 60}m {s['late_s'] % 60}s"
                    if s["late_s"] % 60
                    else f"+{s['late_s'] // 60}m"
                ),
            }
            for s in BIN_SPECS
        ]
    )
    mo.vstack(
        [
            mo.md("### IBI Tolerance Windows"),
            mo.ui.table(_ref.to_dicts()),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, results_df):
    mo.vstack(
        [
            mo.md("### Per-bin Results"),
            mo.ui.table(results_df.to_dicts()),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
