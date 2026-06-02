import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import time
    from datetime import datetime

    import marimo as mo
    import polars as pl

    from multimodalmodel.benchmark import classify_predictions, compute_accuracy
    from multimodalmodel.charts import make_benchmark_chart
    from multimodalmodel.live_tracker import MIN_RESOLVED_FOR_CHART, PredictionTracker
    from multimodalmodel.mbta import MBTA_SUBWAY_ROUTES, fetch_mbta_predictions, fetch_mbta_vehicles

    return (
        MIN_RESOLVED_FOR_CHART,
        MBTA_SUBWAY_ROUTES,
        PredictionTracker,
        classify_predictions,
        compute_accuracy,
        datetime,
        fetch_mbta_predictions,
        fetch_mbta_vehicles,
        make_benchmark_chart,
        mo,
        pl,
        time,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # IBI ETA Accuracy — MBTA v3 Live

    Polls the **[MBTA v3 REST API](https://api-v3.mbta.com)** (real-time
    predictions and vehicle positions) and scores prediction accuracy using the
    **IBI/TransitApp** methodology.

    While fewer than 10 verified arrivals have been detected the chart shows a
    **preview** using the current prediction horizons.  It automatically switches
    to verified arrival data as stops resolve.

    > **Tip:** A free API key from [api-v3.mbta.com](https://api-v3.mbta.com)
    > removes anonymous rate limits.
    """)
    return


@app.cell
def _(PredictionTracker, mo):
    get_tracker, set_tracker = mo.state(PredictionTracker())
    return get_tracker, set_tracker


@app.cell(hide_code=True)
def _(MBTA_SUBWAY_ROUTES, mo):
    route_picker = mo.ui.dropdown(
        options=MBTA_SUBWAY_ROUTES,
        value="Red",
        label="Route",
    )
    stop_filter = mo.ui.text(
        placeholder="e.g. 70061  (leave blank for all stops on route)",
        label="Stop ID filter (optional)",
    )
    api_key = mo.ui.text(
        placeholder="optional — free at api-v3.mbta.com",
        label="MBTA API key",
        kind="password",
    )
    interval = mo.ui.dropdown(
        options=["15s", "30s", "60s"],
        value="30s",
        label="Poll interval",
    )
    running = mo.ui.switch(label="Live polling")
    mo.vstack([
        mo.hstack([route_picker, stop_filter], gap="1rem"),
        mo.hstack([api_key, interval, running], justify="start", gap="1rem"),
    ], gap="0.5rem")
    return api_key, interval, route_picker, running, stop_filter


@app.cell
def _(interval, mo, running):
    mo.stop(
        not running.value,
        mo.callout(
            mo.md("Toggle **Live polling** above to start fetching MBTA v3 data."),
            kind="info",
        ),
    )
    timer = mo.ui.refresh(default_interval=interval.value)
    timer
    return (timer,)


@app.cell
def _(
    api_key,
    fetch_mbta_predictions,
    fetch_mbta_vehicles,
    get_tracker,
    pl,
    route_picker,
    set_tracker,
    stop_filter,
    time,
    timer,
):
    _now = time.time()
    _route = route_picker.value
    _stop = stop_filter.value.strip() or None
    _key = api_key.value.strip() or None

    _empty_tu = pl.DataFrame(schema={
        "trip_id": pl.String, "route_id": pl.String, "stop_sequence": pl.Int32,
        "stop_id": pl.String, "arrival_time": pl.Float64, "arrival_delay": pl.Int32,
        "snapshot_time": pl.Float64,
    })

    _tracker = get_tracker()
    _fetch_error = None
    _tu_df = _empty_tu

    try:
        _tu_df = fetch_mbta_predictions(_route, _stop, _key, _now)
        _tracker.record_trip_updates(_tu_df, _now)

        _vp_df = fetch_mbta_vehicles(_route, _key, _now)
        _tracker.record_vehicle_positions(_vp_df, _now)

        _tracker.last_fetch_time = _now
        _tracker.fetch_count += 1
    except Exception as _exc:
        _fetch_error = str(_exc)
        _tracker.add_error(_fetch_error)

    set_tracker(_tracker)

    current_tu_df = _tu_df
    now = _now
    fetch_error = _fetch_error
    return current_tu_df, fetch_error, now


@app.cell
def _(
    MIN_RESOLVED_FOR_CHART,
    classify_predictions,
    compute_accuracy,
    current_tu_df,
    get_tracker,
    now,
    pl,
):
    _tracker = get_tracker()
    _resolved_df = _tracker.get_resolved_df()

    if len(_resolved_df) >= MIN_RESOLVED_FOR_CHART:
        _data_df = _resolved_df
        is_preview = False
    else:
        _data_df = _tracker.get_preview_df(current_tu_df, now)
        is_preview = True

    if len(_data_df) > 0:
        _classified = classify_predictions(_data_df)
        _predictions = _classified.filter(_classified["bin"].is_not_null())
        _results, _overall = compute_accuracy(_classified)
    else:
        _predictions = pl.DataFrame(schema={
            "predicted_s": pl.Float64, "actual_s": pl.Float64, "bin": pl.String,
            "error_s": pl.Float64, "is_accurate": pl.Boolean,
            "early_s": pl.Float64, "late_s": pl.Float64,
            "min_s": pl.Float64, "max_s": pl.Float64,
        })
        _results = None
        _overall = None

    predictions_df = _predictions
    results_df = _results
    overall_accuracy = _overall
    return is_preview, overall_accuracy, predictions_df, results_df


@app.cell(hide_code=True)
def _(
    MIN_RESOLVED_FOR_CHART,
    datetime,
    fetch_error,
    get_tracker,
    is_preview,
    mo,
):
    _tracker = get_tracker()

    def _fmt_time(ts: float) -> str:
        if ts == 0.0:
            return "—"
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")

    mo.vstack([
        mo.hstack([
            mo.stat(value=str(_tracker.resolved_count), label="Verified arrivals", bordered=True),
            mo.stat(value=str(_tracker.pending_count), label="Pending predictions", bordered=True),
            mo.stat(value=str(_tracker.fetch_count), label="Polls completed", bordered=True),
            mo.stat(value=_fmt_time(_tracker.last_fetch_time), label="Last fetch", bordered=True),
        ], justify="start"),
        mo.callout(
            mo.md(
                f"**Preview mode** — showing live prediction horizons (error shown as 0 "
                f"because MBTA v3 bakes delay into `arrival_time`). "
                f"Switches to verified data after "
                f"**{max(0, MIN_RESOLVED_FOR_CHART - _tracker.resolved_count)} more** stops resolve."
            ),
            kind="info",
        ) if is_preview else mo.md(""),
        mo.callout(mo.md(f"**Fetch error:** {fetch_error}"), kind="warn") if fetch_error else mo.md(""),
        mo.callout(
            mo.md(f"**Last error:** {_tracker.errors[-1]}"), kind="warn",
        ) if _tracker.errors and not fetch_error else mo.md(""),
    ], gap="0.5rem")
    return


@app.cell(hide_code=True)
def _(make_benchmark_chart, mo, overall_accuracy, predictions_df, results_df):
    if len(predictions_df) == 0:
        mo.md("_No predictions in IBI range yet — waiting for data…_")
    else:
        _caption = (
            "Great (≥90%)" if overall_accuracy >= 90
            else "Good (≥80%)" if overall_accuracy >= 80
            else "Needs improvement"
        )
        mo.vstack([
            mo.hstack([
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
            ], justify="start"),
            mo.ui.plotly(make_benchmark_chart(predictions_df)),
        ])
    return


@app.cell(hide_code=True)
def _(mo, results_df):
    if results_df is not None:
        mo.vstack([
            mo.md("### Per-bin Results"),
            mo.ui.table(results_df.to_dicts()),
        ])
    return


if __name__ == "__main__":
    app.run()
