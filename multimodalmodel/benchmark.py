"""Core IBI/TransitApp ETA accuracy benchmark logic."""

import polars as pl

BIN_SPECS: list[dict] = [
    {"label": "0-3 min", "min_s": 0, "max_s": 180, "early_s": 30, "late_s": 90},
    {"label": "3-6 min", "min_s": 180, "max_s": 360, "early_s": 60, "late_s": 150},
    {"label": "6-10 min", "min_s": 360, "max_s": 600, "early_s": 60, "late_s": 210},
    {"label": "10-15 min", "min_s": 600, "max_s": 900, "early_s": 90, "late_s": 270},
]


def generate_sample_data(n: int = 200, seed: int = 42) -> pl.DataFrame:
    """Return a DataFrame of synthetic (predicted_s, actual_s) rows."""
    import random

    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        spec = rng.choice(BIN_SPECS)
        predicted = rng.uniform(spec["min_s"], spec["max_s"])
        error = rng.gauss(15, 55)
        actual = max(0.0, predicted + error)
        rows.append({"predicted_s": round(predicted, 1), "actual_s": round(actual, 1)})
    return pl.DataFrame(rows)


def classify_predictions(df: pl.DataFrame) -> pl.DataFrame:
    """Add bin, error_s, and is_accurate columns to a predictions DataFrame.

    Args:
        df: DataFrame with columns ``predicted_s`` and ``actual_s`` (seconds).

    Returns:
        Extended DataFrame. Rows outside the 0–15 min range have ``bin=null``
        and are excluded from accuracy scoring.
    """
    bin_expr = (
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

    df = df.with_columns(
        [
            bin_expr.alias("bin"),
            (pl.col("actual_s") - pl.col("predicted_s")).alias("error_s"),
        ]
    )

    specs_df = pl.DataFrame(BIN_SPECS).rename({"label": "bin"})
    df = df.join(specs_df, on="bin", how="left").with_columns(
        (
            (pl.col("error_s") >= -pl.col("early_s"))
            & (pl.col("error_s") <= pl.col("late_s"))
        ).alias("is_accurate")
    )
    return df


def classify_predictions_by_stop(
    resolved_stops_df: pl.DataFrame,
    selected_bins: frozenset[str] | None = None,
) -> pl.DataFrame:
    """Aggregate IBI accuracy counts per stop from resolved stop metadata.

    Args:
        resolved_stops_df: Output of :meth:`PredictionTracker.get_resolved_stops_df`.
            Must contain ``stop_id``, ``stop_sequence``, ``predicted_s``, ``actual_s``.
        selected_bins: IBI bin labels to include (e.g. ``{"0-3 min", "3-6 min"}``).
            ``None`` → include all four bins.

    Returns:
        DataFrame with ``stop_id``, ``stop_sequence``, ``correct_count``,
        ``incorrect_count`` — one row per unique (stop_id, stop_sequence).
    """
    empty = pl.DataFrame({
        "stop_id": pl.Series([], dtype=pl.String),
        "stop_sequence": pl.Series([], dtype=pl.Int32),
        "correct_count": pl.Series([], dtype=pl.Int32),
        "incorrect_count": pl.Series([], dtype=pl.Int32),
    })
    if resolved_stops_df.is_empty():
        return empty

    classified = classify_predictions(
        resolved_stops_df.select(["predicted_s", "actual_s"])
    ).with_columns([
        resolved_stops_df["stop_id"],
        resolved_stops_df["stop_sequence"],
    ])

    in_range = classified.filter(pl.col("bin").is_not_null())
    if selected_bins is not None:
        in_range = in_range.filter(pl.col("bin").is_in(list(selected_bins)))

    if in_range.is_empty():
        return empty

    return (
        in_range
        .group_by(["stop_id", "stop_sequence"])
        .agg([
            pl.col("is_accurate").sum().cast(pl.Int32).alias("correct_count"),
            (~pl.col("is_accurate")).sum().cast(pl.Int32).alias("incorrect_count"),
        ])
        .sort("stop_sequence")
    )


def compute_accuracy(classified: pl.DataFrame) -> tuple[pl.DataFrame, float]:
    """Aggregate per-bin accuracy from a classified predictions DataFrame.

    Args:
        classified: Output of :func:`classify_predictions`.

    Returns:
        ``(results_df, overall_accuracy)`` where *results_df* has columns
        ``bin``, ``accurate_n``, ``total_n``, ``accuracy_pct`` and
        *overall_accuracy* is the unweighted mean across bins (0–100).
    """
    bin_order = [s["label"] for s in BIN_SPECS]
    agg = (
        classified.filter(pl.col("bin").is_not_null())
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

    all_bins = pl.DataFrame({"bin": bin_order})
    results_df = all_bins.join(agg, on="bin", how="left").with_columns(
        [
            pl.col("accurate_n").fill_null(0),
            pl.col("total_n").fill_null(0),
            pl.col("accuracy_pct").fill_null(0.0),
        ]
    )
    overall_accuracy = float(results_df["accuracy_pct"].mean())
    return results_df, overall_accuracy
