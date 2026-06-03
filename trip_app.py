import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import random
    import time
    from datetime import datetime

    import marimo as mo
    import polars as pl

    from multimodalmodel.benchmark import BIN_SPECS, classify_predictions_by_stop
    from multimodalmodel.charts import make_trip_profile_chart
    from multimodalmodel.live_tracker import (
        MIN_RESOLVED_FOR_CHART,
        PredictionTracker,
        build_trip_profile_df,
    )

    return (
        BIN_SPECS,
        MIN_RESOLVED_FOR_CHART,
        PredictionTracker,
        build_trip_profile_df,
        classify_predictions_by_stop,
        datetime,
        make_trip_profile_chart,
        mo,
        pl,
        random,
        time,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # GTFS-RT Trip Profile — Per-Stop Arrival Analysis

    Plots each stop's **scheduled vs actual arrival time** for a single trip,
    with a bottom strip showing IBI prediction accuracy counts per stop.

    Use the **bin checkboxes** to filter which prediction horizons are included
    in the accuracy counts.  Toggle **Simulation** to generate realistic
    MBTA Red Line demo data without a live feed.
    """)
    return


# ── Tracker state ──────────────────────────────────────────────────────────────

@app.cell
def _(PredictionTracker, mo):
    get_tracker, set_tracker = mo.state(PredictionTracker())
    return get_tracker, set_tracker


# ── Bin-filter state (source of truth for all checkboxes) ─────────────────────

@app.cell
def _(mo):
    BIN_LABELS = ["0-3 min", "3-6 min", "6-10 min", "10-15 min"]
    get_sel, set_sel = mo.state(frozenset(BIN_LABELS))
    return BIN_LABELS, get_sel, set_sel


# ── "All" checkbox — initialised from bin-selection state ─────────────────────

@app.cell
def _(BIN_LABELS, get_sel, mo):
    all_cb = mo.ui.checkbox(label="All", value=(len(get_sel()) == len(BIN_LABELS)))
    return (all_cb,)


# ── Individual bin checkboxes — each initialised from state ───────────────────

@app.cell
def _(BIN_LABELS, get_sel, mo):
    bin_cbs = mo.ui.array([
        mo.ui.checkbox(label=b, value=(b in get_sel()))
        for b in BIN_LABELS
    ])
    return (bin_cbs,)


# ── "All" checkbox → state: selecting All checks every bin ────────────────────
# Only fires set_sel when all_cb is True, preventing the cascade that would
# occur if we also called set_sel on all_cb=False (state would loop).

@app.cell
def _(BIN_LABELS, all_cb, set_sel):
    if all_cb.value:
        set_sel(frozenset(BIN_LABELS))
    return


# ── Individual checkboxes → state: unchecking one unchecks All ────────────────

@app.cell
def _(BIN_LABELS, bin_cbs, set_sel):
    set_sel(frozenset(l for l, v in zip(BIN_LABELS, bin_cbs.value) if v))
    return


# ── Display checkbox row ───────────────────────────────────────────────────────

@app.cell(hide_code=True)
def _(all_cb, bin_cbs, mo):
    mo.vstack([
        mo.md("**Filter by IBI bin** _(uncheck 'All' to enable individual bins)_"),
        mo.hstack([all_cb, *bin_cbs.elements], gap="1.5rem", align="center"),
    ], gap="0.25rem")
    return


# ── Read the current selected-bin set ─────────────────────────────────────────

@app.cell
def _(get_sel):
    selected_bins = get_sel()
    return (selected_bins,)


# ── Config controls ────────────────────────────────────────────────────────────

@app.cell(hide_code=True)
def _(mo):
    sim_toggle = mo.ui.switch(label="Simulation mode (Red Line demo)", value=True)
    trip_id_input = mo.ui.text(
        placeholder="e.g. canonical-60547000-Red-1-Weekday-01",
        label="Trip ID (simulation uses a fixed demo trip)",
        full_width=True,
    )
    interval = mo.ui.dropdown(options=["10s", "30s", "60s"], value="30s", label="Refresh")
    running = mo.ui.switch(label="Live refresh")
    mo.vstack([
        sim_toggle,
        trip_id_input,
        mo.hstack([interval, running], gap="1rem", justify="start"),
    ], gap="0.5rem")
    return interval, running, sim_toggle, trip_id_input


# ── Simulation data generator ──────────────────────────────────────────────────

@app.cell(hide_code=True)
def _(mo, sim_toggle):
    mo.stop(
        not sim_toggle.value,
        mo.callout(
            mo.md(
                "Simulation is **off**. Enter a GTFS-RT trip ID above and enable "
                "**Live refresh** to load from the tracker."
            ),
            kind="info",
        ),
    )
    return


@app.cell(hide_code=True)
def _(BIN_SPECS, mo, pl, random, selected_bins, sim_toggle, time):
    mo.stop(not sim_toggle.value)

    import math as _math

    _RL_STOPS = [
        ("70061", "Alewife"), ("70063", "Davis"), ("70065", "Porter"),
        ("70067", "Harvard"), ("70069", "Central"), ("70071", "Kendall/MIT"),
        ("70073", "Charles/MGH"), ("70075", "Park St"),
        ("70077", "Downtown Crossing"), ("70079", "South Station"),
        ("70081", "Broadway"), ("70083", "Andrew"), ("70085", "JFK/UMass"),
        ("70087", "Savin Hill"), ("70089", "Fields Corner"),
        ("70091", "Shawmut"), ("70093", "Ashmont"),
    ]
    _RL_SEG_S = [120, 90, 90, 120, 90, 120, 150, 90, 90, 120, 90, 120, 150, 90, 90, 90]

    _rng = random.Random(42)
    _now = time.time()
    _trip_start = _now - 38 * 60
    _sched = [_trip_start]
    for _s in _RL_SEG_S:
        _sched.append(_sched[-1] + _s)

    _delay = 150.0
    _actual = []
    for _sc in _sched:
        _delay += _rng.gauss(2, 12)
        _actual.append(_sc + max(0.0, _delay))

    _rows = []
    for _i, (_sid, _sname) in enumerate(_RL_STOPS):
        _d = _actual[_i] - _sched[_i]
        _n = _rng.randint(14, 28)
        _ok = _bad = 0
        for _ in range(_n):
            _ps = _rng.uniform(20, 890)
            _as = max(0.0, _ps + _rng.gauss(_d * 0.6, 48))
            for _spec in BIN_SPECS:
                if _spec["min_s"] <= _ps < _spec["max_s"]:
                    if _spec["label"] not in selected_bins:
                        break  # skip bins not selected
                    _err = _as - _ps
                    if -_spec["early_s"] <= _err <= _spec["late_s"]:
                        _ok += 1
                    else:
                        _bad += 1
                    break
        _rows.append({
            "stop_id": _sid,
            "stop_sequence": _i + 1,
            "stop_name": _sname,
            "scheduled_min": (_sched[_i] - _trip_start) / 60,
            "actual_min": (_actual[_i] - _trip_start) / 60,
            "correct_count": _ok,
            "incorrect_count": _bad,
        })

    sim_profile_df = pl.DataFrame(_rows, schema={
        "stop_id": pl.String, "stop_sequence": pl.Int32, "stop_name": pl.String,
        "scheduled_min": pl.Float64, "actual_min": pl.Float64,
        "correct_count": pl.Int32, "incorrect_count": pl.Int32,
    })
    sim_trip_id = "canonical-60547000-Red-1-Weekday-01"
    return sim_profile_df, sim_trip_id


# ── Live refresh timer ─────────────────────────────────────────────────────────

@app.cell
def _(interval, mo, running, sim_toggle):
    mo.stop(
        sim_toggle.value or not running.value,
        mo.callout(
            mo.md("Enable **Live refresh** (and disable Simulation) to poll the tracker."),
            kind="info",
        ) if not sim_toggle.value else mo.md(""),
    )
    timer = mo.ui.refresh(default_interval=interval.value)
    timer
    return (timer,)


# ── Build profile_df from tracker (live mode) ──────────────────────────────────

@app.cell
def _(
    build_trip_profile_df,
    get_tracker,
    mo,
    pl,
    selected_bins,
    sim_toggle,
    timer,
    trip_id_input,
):
    mo.stop(sim_toggle.value)
    _tid = trip_id_input.value.strip()
    mo.stop(not _tid, mo.callout(mo.md("Enter a **Trip ID** above."), kind="warn"))

    live_profile_df = build_trip_profile_df(
        _tid,
        get_tracker(),
        selected_bins=selected_bins if selected_bins else None,
    )
    live_trip_id = _tid
    return live_profile_df, live_trip_id


# ── Choose profile_df source ───────────────────────────────────────────────────

@app.cell
def _(mo, sim_toggle):
    _using_sim = sim_toggle.value

    def _pick(sim_val, live_val):
        return sim_val if _using_sim else live_val

    mo.stop(False)  # always pass through
    return (_pick,)


# ── Status + chart ────────────────────────────────────────────────────────────

@app.cell(hide_code=True)
def _(
    _pick,
    make_trip_profile_chart,
    mo,
    sim_profile_df,
    sim_toggle,
    sim_trip_id,
):
    mo.stop(not sim_toggle.value)
    _df = sim_profile_df
    _tid = sim_trip_id

    _total_ok = int(_df["correct_count"].sum())
    _total_bad = int(_df["incorrect_count"].sum())
    _total = _total_ok + _total_bad
    _pct = _total_ok / _total * 100 if _total else 0.0

    mo.vstack([
        mo.hstack([
            mo.stat(value=f"{_pct:.1f}%", label="Overall IBI Accuracy", bordered=True),
            mo.stat(value=str(_total_ok), label="Accurate predictions", bordered=True),
            mo.stat(value=str(_total_bad), label="Inaccurate predictions", bordered=True),
            mo.stat(value=str(len(_df)), label="Stops in trip", bordered=True),
        ], justify="start"),
        mo.ui.plotly(make_trip_profile_chart(_df, trip_id=_tid)),
    ])
    return


@app.cell(hide_code=True)
def _(
    live_profile_df,
    live_trip_id,
    make_trip_profile_chart,
    mo,
    sim_toggle,
):
    mo.stop(sim_toggle.value)
    _df = live_profile_df
    _tid = live_trip_id

    if _df.is_empty():
        mo.callout(mo.md("No resolved stops yet for this trip."), kind="info")
    else:
        _total_ok = int(_df["correct_count"].sum())
        _total_bad = int(_df["incorrect_count"].sum())
        _total = _total_ok + _total_bad
        _pct = _total_ok / _total * 100 if _total else 0.0

        mo.vstack([
            mo.hstack([
                mo.stat(value=f"{_pct:.1f}%", label="Overall IBI Accuracy", bordered=True),
                mo.stat(value=str(_total_ok), label="Accurate predictions", bordered=True),
                mo.stat(value=str(_total_bad), label="Inaccurate predictions", bordered=True),
                mo.stat(value=str(len(_df)), label="Stops in trip", bordered=True),
            ], justify="start"),
            mo.ui.plotly(make_trip_profile_chart(_df, trip_id=_tid)),
        ])
    return


if __name__ == "__main__":
    app.run()
