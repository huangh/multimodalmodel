"""Plotly chart builders for the IBI ETA accuracy benchmark."""

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from multimodalmodel.benchmark import BIN_SPECS


def make_trip_profile_chart(
    trip_profile_df: pl.DataFrame,
    trip_id: str | None = None,
    bar_width_min: float = 1.2,
) -> go.Figure:
    """Build a two-panel trip profile chart.

    Top panel (72%): scheduled arrival vs actual arrival per stop with a
    diagonal on-time reference line and delay shading.

    Bottom panel (28%): stacked bar per stop showing IBI-correct (green) and
    IBI-incorrect (red) prediction counts from :func:`build_trip_profile_df`.

    Args:
        trip_profile_df: One row per stop — output of
            :func:`~multimodalmodel.live_tracker.build_trip_profile_df`.
            Columns: ``stop_id``, ``stop_sequence``, ``stop_name``,
            ``scheduled_min``, ``actual_min`` (nullable), ``correct_count``,
            ``incorrect_count``.
        trip_id: Shown in the chart title when provided.
        bar_width_min: Width of each bar in x-axis minutes.

    Returns:
        Plotly :class:`~plotly.graph_objects.Figure` with two linked subplots.
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
    )

    if trip_profile_df.is_empty():
        fig.add_annotation(
            text="No trip data available yet",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888"),
        )
        fig.update_layout(template="plotly_white", height=600)
        return fig

    df = trip_profile_df.sort("stop_sequence")
    sched = df["scheduled_min"].to_list()
    raw_actual = df["actual_min"].to_list()
    names = df["stop_name"].to_list()

    # Split resolved vs pending stops
    resolved_idx = [i for i, a in enumerate(raw_actual) if a is not None]
    unresolved_idx = [i for i, a in enumerate(raw_actual) if a is None]

    r_sched = [sched[i] for i in resolved_idx]
    r_actual = [raw_actual[i] for i in resolved_idx]
    r_names = [names[i] for i in resolved_idx]

    u_sched = [sched[i] for i in unresolved_idx]
    u_names = [names[i] for i in unresolved_idx]

    # ── Top panel ──────────────────────────────────────────────────────── #

    x_min = min(sched)
    x_max = max(sched)

    # Diagonal reference y = x (perfect on-time)
    fig.add_trace(
        go.Scatter(
            x=[x_min, x_max],
            y=[x_min, x_max],
            mode="lines",
            line=dict(color="rgba(160,160,160,0.8)", width=1.5, dash="dash"),
            showlegend=False,
            hoverinfo="skip",
            name="On-time reference",
        ),
        row=1, col=1,
    )

    # Delay fill between diagonal and trajectory (resolved stops only)
    if len(r_sched) >= 2:
        fig.add_trace(
            go.Scatter(
                x=r_sched,
                y=r_actual,
                mode="none",
                fill="tonexty",
                fillcolor="rgba(231,76,60,0.12)",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1, col=1,
        )

    # Trajectory connecting line
    if len(r_sched) >= 2:
        fig.add_trace(
            go.Scatter(
                x=r_sched,
                y=r_actual,
                mode="lines",
                line=dict(color="#555555", width=1.5),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1, col=1,
        )

    # Resolved stop dots — colored green (on-time / early) or red (late)
    if r_sched:
        dot_colors = [
            "#2ecc71" if (a - s) <= 1.0 else "#e74c3c"
            for s, a in zip(r_sched, r_actual)
        ]
        hover = [
            f"<b>{n}</b><br>Scheduled: {s:.1f} min<br>Actual: {a:.1f} min"
            f"<br>Delay: {(a - s) * 60:+.0f} s"
            for n, s, a in zip(r_names, r_sched, r_actual)
        ]
        fig.add_trace(
            go.Scatter(
                x=r_sched,
                y=r_actual,
                mode="markers",
                marker=dict(
                    color=dot_colors,
                    size=10,
                    line=dict(color="white", width=1.5),
                ),
                text=hover,
                hoverinfo="text",
                showlegend=False,
            ),
            row=1, col=1,
        )

    # Unresolved stops — open circles sitting on the diagonal
    if u_sched:
        fig.add_trace(
            go.Scatter(
                x=u_sched,
                y=u_sched,
                mode="markers",
                marker=dict(
                    symbol="circle-open",
                    color="#aaaaaa",
                    size=9,
                    line=dict(width=2),
                ),
                text=[f"<b>{n}</b><br>Pending arrival" for n in u_names],
                hoverinfo="text",
                name="Pending",
                showlegend=bool(u_sched),
            ),
            row=1, col=1,
        )

    # ── Bottom panel ───────────────────────────────────────────────────── #

    correct = df["correct_count"].to_list()
    incorrect = df["incorrect_count"].to_list()
    widths = [bar_width_min] * len(sched)

    fig.add_trace(
        go.Bar(
            x=sched,
            y=correct,
            name="Accurate (IBI)",
            marker_color="#2ecc71",
            marker_line=dict(color="white", width=0.5),
            width=widths,
            text=[str(c) if c > 0 else "" for c in correct],
            textposition="inside",
            hovertemplate="<b>%{customdata}</b><br>Accurate: %{y}<extra></extra>",
            customdata=names,
        ),
        row=2, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=sched,
            y=incorrect,
            name="Inaccurate (IBI)",
            marker_color="#e74c3c",
            marker_line=dict(color="white", width=0.5),
            width=widths,
            text=[str(c) if c > 0 else "" for c in incorrect],
            textposition="inside",
            hovertemplate="<b>%{customdata}</b><br>Inaccurate: %{y}<extra></extra>",
            customdata=names,
        ),
        row=2, col=1,
    )

    # ── Layout ─────────────────────────────────────────────────────────── #

    title = f"Trip Profile{': ' + trip_id if trip_id else ''}"
    fig.update_layout(
        title=title,
        barmode="stack",
        template="plotly_white",
        height=600,
        legend=dict(
            orientation="v",
            x=1.01,
            y=0.5,
            xanchor="left",
            bordercolor="#dddddd",
            borderwidth=1,
        ),
        margin=dict(r=200, t=80, b=60),
    )
    fig.update_xaxes(
        title_text="Scheduled arrival (min from trip start)",
        showgrid=False,
        row=2, col=1,
    )
    fig.update_yaxes(title_text="Actual arrival (min)", row=1, col=1)
    fig.update_yaxes(
        title_text="Predictions",
        rangemode="nonnegative",
        row=2, col=1,
    )
    return fig


def _fmt_tolerance(seconds: int, positive: bool) -> str:
    m, s = abs(seconds) // 60, abs(seconds) % 60
    sign = "+" if positive else "-"
    if m and s:
        return f"{sign}{m}m {s}s"
    return f"{sign}{m}m" if m else f"{sign}{s}s"


def make_benchmark_chart(predictions_df: pl.DataFrame) -> go.Figure:
    """Build the IBI/TransitApp ETA accuracy scatter chart.

    Args:
        predictions_df: Classified predictions from
            :func:`~multimodalmodel.benchmark.classify_predictions`, filtered
            to rows where ``bin`` is not null.

    Returns:
        A Plotly :class:`~plotly.graph_objects.Figure`.
    """
    pm = predictions_df["predicted_s"] / 60
    em = predictions_df["error_s"] / 60
    accurate = predictions_df["is_accurate"]
    too_late = ~accurate & (em > predictions_df["late_s"] / 60)
    too_early = ~accurate & (em < -(predictions_df["early_s"] / 60))

    # Staircase boundary lines (x-axis is reversed: 15→0)
    xs = [15.0, 10.0, 10.0, 6.0, 6.0, 3.0, 3.0, 0.0]
    y_up = [4.5, 4.5, 3.5, 3.5, 2.5, 2.5, 1.5, 1.5]
    y_lo = [-1.5, -1.5, -1.0, -1.0, -1.0, -1.0, -0.5, -0.5]

    fig = go.Figure()

    # Green tolerance band
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

    # Bin separator lines
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
            text=_fmt_tolerance(spec["late_s"], positive=True),
            showarrow=False,
            font=dict(size=10, color="#444"),
            yanchor="bottom",
        )
        fig.add_annotation(
            x=xmid,
            y=-spec["early_s"] / 60 - 0.18,
            text=_fmt_tolerance(spec["early_s"], positive=False),
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
        margin=dict(r=220, t=80, b=80),
    )
    return fig
