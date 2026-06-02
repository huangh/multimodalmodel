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
    import polars as pl
    from multimodalmodel.benchmark import BIN_SPECS, classify_predictions, compute_accuracy
    from multimodalmodel.charts import make_benchmark_chart

    return BIN_SPECS, classify_predictions, compute_accuracy, make_benchmark_chart, pl


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
def _(n_predictions, pl, seed):
    import random

    _rng = random.Random(int(seed.value))
    _rows = []
    from multimodalmodel.benchmark import BIN_SPECS as _BIN_SPECS

    for _i in range(int(n_predictions.value)):
        _spec = _rng.choice(_BIN_SPECS)
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
def _(classify_predictions, compute_accuracy, editor, pl):
    _df = pl.DataFrame(editor.value)
    classified_df = classify_predictions(_df)
    results_df, overall_accuracy = compute_accuracy(classified_df)
    predictions_df = classified_df.filter(classified_df["bin"].is_not_null())
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
def _(make_benchmark_chart, mo, predictions_df):
    mo.ui.plotly(make_benchmark_chart(predictions_df))
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
