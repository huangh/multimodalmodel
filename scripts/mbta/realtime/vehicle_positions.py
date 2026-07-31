# /// hub
# title = "Live vehicle positions"
# description = "Current vehicles on a subway line from the MBTA v3 API, with a status breakdown."
# tags = ["mbta", "realtime", "network"]
# params = ["api_key"]
# ///
import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium", app_title="Live vehicle positions")


@app.cell
def _():
    import os

    import marimo as mo
    import polars as pl

    from multimodalmodel.mbta import MBTA_SUBWAY_ROUTES, fetch_mbta_vehicles

    return MBTA_SUBWAY_ROUTES, fetch_mbta_vehicles, mo, os, pl


@app.cell
def _(os):
    # The hub can inject `api_key` via app.embed(defs=...); otherwise fall back
    # to the environment so the script also runs standalone.
    api_key = os.environ.get("MBTA_API_KEY") or None
    return (api_key,)


@app.cell
def _(MBTA_SUBWAY_ROUTES, mo):
    route_picker = mo.ui.dropdown(
        options=MBTA_SUBWAY_ROUTES, value="Red Line", label="route"
    )
    fetch_button = mo.ui.run_button(label="Fetch vehicles")
    mo.hstack([route_picker, fetch_button], justify="start", gap=2, align="end")
    return fetch_button, route_picker


@app.cell
def _(api_key, fetch_button, fetch_mbta_vehicles, mo, route_picker):
    mo.stop(
        not fetch_button.value,
        mo.md("Press **Fetch vehicles** to call the MBTA v3 API."),
    )
    vehicles = fetch_mbta_vehicles(route_id=route_picker.value, api_key=api_key)
    return (vehicles,)


@app.cell
def _(mo, pl, vehicles):
    _status = {0: "incoming at", 1: "stopped at", 2: "in transit to"}
    _summary = (
        vehicles.group_by("current_status")
        .len()
        .with_columns(
            pl.col("current_status")
            .replace_strict(_status, default="unknown")
            .alias("status")
        )
        .select("status", "len")
        .sort("len", descending=True)
    )
    mo.vstack(
        [
            mo.stat(label="Vehicles", value=str(vehicles.height)),
            mo.ui.table(_summary.to_dicts(), selection=None),
            mo.ui.table(
                vehicles.select(
                    "vehicle_id", "trip_id", "stop_id", "stop_sequence", "timestamp"
                ).to_dicts(),
                selection=None,
                page_size=10,
            ),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
