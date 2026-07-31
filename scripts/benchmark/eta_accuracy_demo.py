# /// hub
# title = "ETA accuracy benchmark (synthetic)"
# description = "IBI/TransitApp accuracy bins on generated prediction data. No network required — good for smoke-testing the hub."
# tags = ["benchmark", "synthetic", "offline"]
# ///
import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="ETA accuracy benchmark (synthetic)")


@app.cell
def _():
    import marimo as mo

    from multimodalmodel.benchmark import (
        classify_predictions,
        compute_accuracy,
        generate_sample_data,
    )
    from multimodalmodel.charts import make_benchmark_chart

    return (
        classify_predictions,
        compute_accuracy,
        generate_sample_data,
        make_benchmark_chart,
        mo,
    )


@app.cell
def _(mo):
    n_slider = mo.ui.slider(50, 2000, value=400, step=50, label="samples")
    seed_slider = mo.ui.slider(0, 50, value=0, label="seed")
    mo.hstack([n_slider, seed_slider], justify="start", gap=2)
    return n_slider, seed_slider


@app.cell
def _(
    classify_predictions,
    compute_accuracy,
    generate_sample_data,
    n_slider,
    seed_slider,
):
    samples = generate_sample_data(n=n_slider.value, seed=seed_slider.value)
    classified = classify_predictions(samples)
    results, overall_pct = compute_accuracy(classified)
    return classified, overall_pct, results


@app.cell
def _(classified, make_benchmark_chart, mo, overall_pct, results):
    mo.vstack(
        [
            mo.stat(
                label="Overall accuracy",
                value=f"{overall_pct:.1f}%",
                caption="share of predictions inside the IBI tolerance",
            ),
            mo.ui.plotly(
                make_benchmark_chart(classified.filter(classified["bin"].is_not_null()))
            ),
            mo.ui.table(results.to_dicts(), selection=None),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
