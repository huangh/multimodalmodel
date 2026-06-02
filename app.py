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
    predictions_df = _df.filter(pl.col("bin").is_not_null())
    return overall_accuracy, predictions_df, results_df


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
def _(BIN_SPECS, go, mo, predictions_df):
    # Convert to minutes
    _pm = predictions_df["predicted_s"] / 60
    _em = predictions_df["error_s"] / 60
    _accurate = predictions_df["is_accurate"]
    _too_late = ~_accurate & (_em > predictions_df["late_s"] / 60)
    _too_early = ~_accurate & (_em < -(predictions_df["early_s"] / 60))

    def _fmt(seconds: int, positive: bool) -> str:
        m, s = abs(seconds) // 60, abs(seconds) % 60
        sign = "+" if positive else "-"
        if m and s:
            return f"{sign}{m}m {s}s"
        return f"{sign}{m}m" if m else f"{sign}{s}s"

    # Staircase x/y in minutes — x-axis will be reversed (15→0)
    _xs = [15.0, 10.0, 10.0, 6.0, 6.0, 3.0, 3.0, 0.0]
    _y_up = [4.5, 4.5, 3.5, 3.5, 2.5, 2.5, 1.5, 1.5]
    _y_lo = [-1.5, -1.5, -1.0, -1.0, -1.0, -1.0, -0.5, -0.5]

    _fig = go.Figure()

    # Green fill between lower and upper staircases
    _fig.add_trace(
        go.Scatter(
            x=_xs,
            y=_y_lo,
            mode="lines",
            line=dict(color="rgba(0,168,89,0.75)", width=2),
            fill=None,
            showlegend=False,
            hoverinfo="skip",
        )
    )
    _fig.add_trace(
        go.Scatter(
            x=_xs,
            y=_y_up,
            mode="lines",
            line=dict(color="rgba(0,168,89,0.75)", width=2),
            fill="tonexty",
            fillcolor="rgba(46,204,113,0.18)",
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # Scatter: too late — yellow
    _xl, _yl = _pm.filter(_too_late).to_list(), _em.filter(_too_late).to_list()
    if _xl:
        _fig.add_trace(
            go.Scatter(
                x=_xl,
                y=_yl,
                mode="markers",
                marker=dict(color="#f1c40f", size=9, line=dict(color="white", width=1)),
                name="Excess wait time — Inaccurate ETA",
            )
        )

    # Scatter: accurate — green
    _xa, _ya = _pm.filter(_accurate).to_list(), _em.filter(_accurate).to_list()
    if _xa:
        _fig.add_trace(
            go.Scatter(
                x=_xa,
                y=_ya,
                mode="markers",
                marker=dict(color="#2ecc71", size=9, line=dict(color="white", width=1)),
                name="Catch the ride — Accurate ETA",
            )
        )

    # Scatter: too early — pink
    _xe, _ye = _pm.filter(_too_early).to_list(), _em.filter(_too_early).to_list()
    if _xe:
        _fig.add_trace(
            go.Scatter(
                x=_xe,
                y=_ye,
                mode="markers",
                marker=dict(color="#e91e63", size=9, line=dict(color="white", width=1)),
                name="Miss the ride — Inaccurate ETA",
            )
        )

    # Vertical bin separators
    for _bx in [3.0, 6.0, 10.0]:
        _fig.add_vline(x=_bx, line_dash="dot", line_color="#cccccc", line_width=1.5)

    # Arrival line
    _fig.add_vline(x=0.0, line_color="#2196f3", line_width=2.5)
    _fig.add_annotation(
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

    # Per-bin tolerance labels and category labels
    _cat_labels = [
        "Where is my ride?",
        "Do I need to hustle?",
        "Do I need to leave now?",
        "Is the vehicle coming?",
    ]
    for _i, _spec in enumerate(BIN_SPECS):
        _xmid = (_spec["min_s"] + _spec["max_s"]) / 2 / 60
        _fig.add_annotation(
            x=_xmid,
            y=_spec["late_s"] / 60 + 0.18,
            text=_fmt(_spec["late_s"], positive=True),
            showarrow=False,
            font=dict(size=10, color="#444"),
            yanchor="bottom",
        )
        _fig.add_annotation(
            x=_xmid,
            y=-_spec["early_s"] / 60 - 0.18,
            text=_fmt(_spec["early_s"], positive=False),
            showarrow=False,
            font=dict(size=10, color="#444"),
            yanchor="top",
        )
        _fig.add_annotation(
            x=_xmid,
            y=1.04,
            xref="x",
            yref="paper",
            text=f"<i>{_cat_labels[_i]}</i>",
            showarrow=False,
            font=dict(size=11, color="#777"),
            yanchor="bottom",
        )
        _fig.add_annotation(
            x=_xmid,
            y=-0.08,
            xref="x",
            yref="paper",
            text=f"{_spec['label']} away",
            showarrow=False,
            font=dict(size=11, color="#444"),
            yanchor="top",
        )

    _fig.update_layout(
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
        margin=dict(r=220, t=80, b=80),
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
