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
    from multimodalmodel.gtfs_rt import fetch_feed, parse_trip_updates, parse_vehicle_positions
    from multimodalmodel.live_tracker import MIN_RESOLVED_FOR_CHART, PredictionTracker

    return (
        MIN_RESOLVED_FOR_CHART,
        PredictionTracker,
        classify_predictions,
        compute_accuracy,
        datetime,
        fetch_feed,
        make_benchmark_chart,
        mo,
        parse_trip_updates,
        parse_vehicle_positions,
        pl,
        time,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # IBI ETA Accuracy — Live GTFS-RT

    Polls GTFS-RT trip updates and vehicle positions to compute real-time
    prediction accuracy using the **IBI/TransitApp** methodology.

    While fewer than 10 verified arrivals have been detected the chart shows a
    **preview** derived from the current trip-update delay field.  It
    automatically switches to verified data as arrivals accumulate.
    """)
    return


@app.cell
def _(PredictionTracker, mo):
    get_tracker, set_tracker = mo.state(PredictionTracker())
    return get_tracker, set_tracker


@app.cell(hide_code=True)
def _(mo):
    primary_url = mo.ui.text(
        placeholder="https://api.example.com/gtfs-rt/TripUpdates.pb",
        label="GTFS-RT URL (trip updates — also used for vehicle positions unless overridden)",
        full_width=True,
    )
    vp_url_override = mo.ui.text(
        placeholder="https://api.example.com/gtfs-rt/VehiclePositions.pb  (optional)",
        label="Vehicle positions URL override (leave blank to use the URL above)",
        full_width=True,
    )
    api_key = mo.ui.text(
        placeholder="your-api-key",
        label="API key (sent as X-API-Key header — leave blank if not required)",
        kind="password",
    )
    interval = mo.ui.dropdown(
        options=["10s", "15s", "30s", "60s"],
        value="30s",
        label="Poll interval",
    )
    running = mo.ui.switch(label="Live polling")
    mo.vstack([
        primary_url,
        vp_url_override,
        mo.hstack([api_key, interval, running], justify="start", gap="1rem"),
    ], gap="0.5rem")
    return api_key, interval, primary_url, running, vp_url_override


@app.cell
def _(mo, running, interval):
    mo.stop(
        not running.value,
        mo.callout(
            mo.md("Toggle **Live polling** above to start fetching GTFS-RT data."),
            kind="info",
        ),
    )
    timer = mo.ui.refresh(default_interval=interval.value)
    timer
    return (timer,)


@app.cell
def _(
    api_key,
    fetch_feed,
    get_tracker,
    parse_trip_updates,
    parse_vehicle_positions,
    pl,
    primary_url,
    set_tracker,
    time,
    timer,
    vp_url_override,
):
    _now = time.time()
    _headers = {"X-API-Key": api_key.value} if api_key.value.strip() else {}
    _vp_url = vp_url_override.value.strip() or primary_url.value.strip()

    _empty_tu = pl.DataFrame(schema={
        "trip_id": pl.String, "route_id": pl.String, "stop_sequence": pl.Int32,
        "stop_id": pl.String, "arrival_time": pl.Float64, "arrival_delay": pl.Int32,
        "snapshot_time": pl.Float64,
    })

    _tracker = get_tracker()
    _fetch_error = None
    _tu_df = _empty_tu

    mo.stop(
        not primary_url.value.strip(),
        mo.callout(mo.md("Enter a **GTFS-RT URL** in the field above."), kind="warn"),
    )

    try:
        _tu_bytes = fetch_feed(primary_url.value.strip(), _headers)
        _tu_df = parse_trip_updates(_tu_bytes, _now)
        _tracker.record_trip_updates(_tu_df, _now)

        _vp_bytes = fetch_feed(_vp_url, _headers)
        _vp_df = parse_vehicle_positions(_vp_bytes, _now)
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
    datetime,
    fetch_error,
    get_tracker,
    is_preview,
    mo,
    MIN_RESOLVED_FOR_CHART,
):
    _tracker = get_tracker()

    def _fmt_time(ts: float) -> str:
        if ts == 0.0:
            return "—"
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")

    mo.vstack([
        mo.hstack([
            mo.stat(
                value=str(_tracker.resolved_count),
                label="Verified arrivals",
                bordered=True,
            ),
            mo.stat(
                value=str(_tracker.pending_count),
                label="Pending predictions",
                bordered=True,
            ),
            mo.stat(
                value=str(_tracker.fetch_count),
                label="Polls completed",
                bordered=True,
            ),
            mo.stat(
                value=_fmt_time(_tracker.last_fetch_time),
                label="Last fetch",
                bordered=True,
            ),
        ], justify="start"),
        mo.callout(
            mo.md(
                f"**Preview mode** — showing current delay data as a proxy for accuracy.  "
                f"Chart switches to verified arrivals after "
                f"**{max(0, MIN_RESOLVED_FOR_CHART - _tracker.resolved_count)} more** "
                f"stops resolve."
            ),
            kind="info",
        ) if is_preview else mo.md(""),
        mo.callout(
            mo.md(f"**Fetch error:** {fetch_error}"),
            kind="warn",
        ) if fetch_error else mo.md(""),
        mo.callout(
            mo.md(f"**Last error:** {_tracker.errors[-1]}"),
            kind="warn",
        ) if _tracker.errors and not fetch_error else mo.md(""),
    ], gap="0.5rem")
    return


@app.cell(hide_code=True)
def _(make_benchmark_chart, mo, overall_accuracy, predictions_df, results_df):
    if len(predictions_df) == 0:
        mo.md("_No data in IBI range yet — waiting for predictions…_")
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
