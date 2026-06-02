"""Plotly chart builders for the IBI ETA accuracy benchmark."""

import plotly.graph_objects as go
import polars as pl

from multimodalmodel.benchmark import BIN_SPECS


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
