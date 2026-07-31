# /// hub
# title = "Prediction horizon distribution"
# description = "How far ahead the MBTA is predicting right now, per route — the denominator behind every accuracy bin."
# tags = ["mbta", "realtime", "network", "predictions"]
# params = ["api_key"]
# ///
import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="Prediction horizon distribution")


@app.cell
def _():
    import os
    import time

    import marimo as mo
    import plotly.graph_objects as go
    import polars as pl

    from multimodalmodel.mbta import MBTA_SUBWAY_ROUTES, fetch_mbta_predictions

    return MBTA_SUBWAY_ROUTES, fetch_mbta_predictions, go, mo, os, pl, time


@app.cell
def _(os):
    api_key = os.environ.get("MBTA_API_KEY") or None
    return (api_key,)


@app.cell
def _(MBTA_SUBWAY_ROUTES, mo):
    route_picker = mo.ui.dropdown(
        options=MBTA_SUBWAY_ROUTES, value="Orange Line", label="route"
    )
    fetch_button = mo.ui.run_button(label="Fetch predictions")
    mo.hstack([route_picker, fetch_button], justify="start", gap=2, align="end")
    return fetch_button, route_picker


@app.cell
def _(api_key, fetch_button, fetch_mbta_predictions, mo, pl, route_picker, time):
    mo.stop(
        not fetch_button.value,
        mo.md("Press **Fetch predictions** to call the MBTA v3 API."),
    )
    _now = time.time()
    horizons = (
        fetch_mbta_predictions(route_id=route_picker.value, api_key=api_key)
        .with_columns(((pl.col("arrival_time") - _now) / 60).alias("horizon_min"))
        .filter(pl.col("horizon_min") > 0)
    )
    return (horizons,)


@app.cell
def _(go, horizons, mo):
    mo.stop(horizons.is_empty(), mo.md("No upcoming predictions returned."))
    _fig = go.Figure(go.Histogram(x=horizons["horizon_min"].to_list(), nbinsx=30))
    _fig.update_layout(
        title="Minutes until predicted arrival",
        xaxis_title="horizon (min)",
        yaxis_title="predictions",
        height=380,
    )
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(label="Predictions", value=str(horizons.height)),
                    mo.stat(
                        label="Median horizon",
                        value=f"{horizons['horizon_min'].median():.1f} min",
                    ),
                    mo.stat(
                        label="Max horizon",
                        value=f"{horizons['horizon_min'].max():.1f} min",
                    ),
                ],
                justify="start",
                gap=2,
            ),
            mo.ui.plotly(_fig),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
