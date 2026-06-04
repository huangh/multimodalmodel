"""Stateful accumulation of GTFS-RT predictions and actual arrivals."""

from dataclasses import dataclass, field

import polars as pl

# IBI benchmark max horizon — skip predictions beyond 15 min
_MAX_HORIZON_S = 900
# After this many resolved pairs the preview switches to verified data
MIN_RESOLVED_FOR_CHART = 10
# Drop pending entries whose predicted arrival is older than this
_STALE_THRESHOLD_S = 3600

_RESOLVED_META_SCHEMA = {
    "trip_id": pl.String,
    "stop_id": pl.String,
    "stop_sequence": pl.Int32,
    "scheduled_unix": pl.Float64,
    "actual_unix": pl.Float64,
    "predicted_s": pl.Float64,
    "actual_s": pl.Float64,
}

_PROFILE_SCHEMA = {
    "stop_id": pl.String,
    "stop_sequence": pl.Int32,
    "stop_name": pl.String,
    "scheduled_min": pl.Float64,
    "actual_min": pl.Float64,
    "correct_count": pl.Int32,
    "incorrect_count": pl.Int32,
}


@dataclass
class PredictionTracker:
    """Accumulates GTFS-RT predictions and resolves them against actual arrivals.

    Call :meth:`record_trip_updates` and :meth:`record_vehicle_positions` on
    each polling cycle, then read :meth:`get_resolved_df` to feed the IBI
    benchmark chart.
    """

    # (trip_id, stop_id) → list of (snapshot_time, predicted_arrival_unix, scheduled_unix, stop_seq)
    pending: dict = field(default_factory=dict)
    # Finalised (predicted_s, actual_s) pairs ready for the benchmark — unchanged public API
    resolved: list = field(default_factory=list)
    # Richer per-stop metadata for the trip profile chart
    resolved_with_meta: list = field(default_factory=list)
    # trip_id → (current_stop_sequence, arrival_timestamp)
    last_stop_seq: dict = field(default_factory=dict)
    # trip_id → {stop_sequence: stop_id}  — learned from trip updates
    trip_seq_to_stop: dict = field(default_factory=dict)
    # Rolling list of the last 10 fetch errors for the status bar
    errors: list = field(default_factory=list)
    last_fetch_time: float = 0.0
    fetch_count: int = 0

    # ------------------------------------------------------------------ #
    # Public mutators                                                      #
    # ------------------------------------------------------------------ #

    def record_trip_updates(self, df: pl.DataFrame, snapshot_time: float) -> None:
        """Store predictions from a trip-update DataFrame.

        Args:
            df: Output of :func:`~multimodalmodel.gtfs_rt.parse_trip_updates`.
            snapshot_time: Unix timestamp of the poll that produced *df*.
        """
        if df.is_empty():
            return

        for row in df.iter_rows(named=True):
            trip_id = row["trip_id"]
            stop_id = row["stop_id"]
            stop_seq = row["stop_sequence"]
            arrival_time = row["arrival_time"]
            arrival_delay = row["arrival_delay"]

            if not trip_id:
                continue
            if arrival_time <= snapshot_time:
                continue  # already past

            # Scheduled arrival = real-time prediction minus reported delay
            scheduled_unix = float(arrival_time) - float(arrival_delay)

            key = (trip_id, stop_id)
            if key not in self.pending:
                self.pending[key] = []
            self.pending[key].append(
                (snapshot_time, arrival_time, scheduled_unix, int(stop_seq))
            )

            # Build sequence→stop_id mapping for arrival detection
            if trip_id not in self.trip_seq_to_stop:
                self.trip_seq_to_stop[trip_id] = {}
            self.trip_seq_to_stop[trip_id][stop_seq] = stop_id

        self._cleanup_stale_pending(snapshot_time)

    def record_vehicle_positions(self, df: pl.DataFrame, snapshot_time: float) -> None:
        """Detect stop arrivals from a vehicle-positions DataFrame and resolve pending predictions.

        Two detection paths:
        - ``STOPPED_AT`` (status 1): vehicle is at stop right now → resolve immediately.
        - Stop-sequence advance: sequence jumped → all skipped stops have been passed.

        Args:
            df: Output of :func:`~multimodalmodel.gtfs_rt.parse_vehicle_positions`.
            snapshot_time: Unix timestamp of the poll.
        """
        if df.is_empty():
            return

        for row in df.iter_rows(named=True):
            trip_id = row["trip_id"]
            if not trip_id:
                continue

            current_seq = row["stop_sequence"]
            stop_id = row["stop_id"]
            status = row["current_status"]
            vp_time = row["timestamp"] or snapshot_time

            # Path 1: vehicle is currently stopped at this stop
            if status == 1 and stop_id:
                self._resolve_stop(trip_id, stop_id, vp_time)

            # Path 2: stop-sequence advanced → passed stops have arrived
            prev_info = self.last_stop_seq.get(trip_id)
            prev_seq = prev_info[0] if prev_info is not None else -1

            if current_seq > 0 and current_seq > prev_seq:
                seq_map = self.trip_seq_to_stop.get(trip_id, {})
                for seq, sid in seq_map.items():
                    if prev_seq < seq < current_seq:
                        self._resolve_stop(trip_id, sid, vp_time)
                self.last_stop_seq[trip_id] = (current_seq, vp_time)
            elif current_seq == 0 and prev_seq > 0:
                # Trip reset (new service run)
                self.last_stop_seq[trip_id] = (0, vp_time)

    # ------------------------------------------------------------------ #
    # Public readers                                                       #
    # ------------------------------------------------------------------ #

    def get_resolved_df(self) -> pl.DataFrame:
        """Return all verified (predicted_s, actual_s) pairs as a DataFrame."""
        if not self.resolved:
            return pl.DataFrame({"predicted_s": pl.Series([], dtype=pl.Float64),
                                 "actual_s":    pl.Series([], dtype=pl.Float64)})
        predicted, actual = zip(*self.resolved)
        return pl.DataFrame({"predicted_s": list(predicted), "actual_s": list(actual)})

    def get_resolved_stops_df(self) -> pl.DataFrame:
        """Return per-stop resolved metadata for trip profile analysis."""
        if not self.resolved_with_meta:
            return pl.DataFrame(schema=_RESOLVED_META_SCHEMA)
        return pl.DataFrame(self.resolved_with_meta, schema=_RESOLVED_META_SCHEMA)

    def get_preview_df(self, trip_updates_df: pl.DataFrame, now: float) -> pl.DataFrame:
        """Return a proxy accuracy DataFrame from current trip-update delay data.

        Uses each stop's current predicted TTA as ``predicted_s`` and shifts it
        by ``arrival_delay`` to estimate where the actual arrival would fall.
        Only includes stops with a future predicted arrival within the IBI range.

        Args:
            trip_updates_df: Most recent trip-update DataFrame from a poll.
            now: Current Unix timestamp.
        """
        empty = pl.DataFrame({"predicted_s": pl.Series([], dtype=pl.Float64),
                              "actual_s":    pl.Series([], dtype=pl.Float64)})
        if trip_updates_df is None or trip_updates_df.is_empty():
            return empty

        rows: list[dict] = []
        for row in trip_updates_df.iter_rows(named=True):
            predicted_s = row["arrival_time"] - now
            if predicted_s <= 0 or predicted_s > _MAX_HORIZON_S:
                continue
            # delay > 0 → vehicle running late → actual_s > predicted_s
            actual_s = predicted_s + float(row["arrival_delay"])
            if actual_s < 0:
                continue
            rows.append({"predicted_s": predicted_s, "actual_s": actual_s})

        if not rows:
            return empty
        return pl.DataFrame(rows)

    def add_error(self, msg: str) -> None:
        """Append an error message, keeping at most the last 10."""
        self.errors = (self.errors + [msg])[-10:]

    @property
    def pending_count(self) -> int:
        return sum(len(v) for v in self.pending.values())

    @property
    def resolved_count(self) -> int:
        return len(self.resolved)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _resolve_stop(self, trip_id: str, stop_id: str, actual_arrival_time: float) -> None:
        key = (trip_id, stop_id)
        if key not in self.pending:
            return
        for t_snap, pred_arrival, scheduled_unix, stop_seq in self.pending[key]:
            predicted_s = pred_arrival - t_snap
            actual_s = actual_arrival_time - t_snap
            if 0 < predicted_s <= _MAX_HORIZON_S and actual_s >= 0:
                self.resolved.append((predicted_s, actual_s))
                self.resolved_with_meta.append({
                    "trip_id": trip_id,
                    "stop_id": stop_id,
                    "stop_sequence": stop_seq,
                    "scheduled_unix": scheduled_unix,
                    "actual_unix": actual_arrival_time,
                    "predicted_s": predicted_s,
                    "actual_s": actual_s,
                })
        del self.pending[key]

    def _cleanup_stale_pending(self, now: float) -> None:
        stale = [
            key for key, preds in self.pending.items()
            if all(p[1] < now - _STALE_THRESHOLD_S for p in preds)
        ]
        for key in stale:
            del self.pending[key]


def build_trip_profile_df(
    trip_id: str,
    tracker: PredictionTracker,
    trip_start_unix: float | None = None,
    stop_name_map: dict[str, str] | None = None,
    selected_bins: frozenset[str] | None = None,
) -> pl.DataFrame:
    """Build a trip profile DataFrame for :func:`~multimodalmodel.charts.make_trip_profile_chart`.

    Args:
        trip_id: The trip to profile.
        tracker: Tracker with resolved_with_meta populated.
        trip_start_unix: Unix timestamp of the first scheduled stop.
            Defaults to the minimum ``scheduled_unix`` seen for this trip.
        stop_name_map: Optional ``{stop_id: display_name}`` for hover labels.
        selected_bins: IBI bins to include in correct/incorrect counts.
            ``None`` → all bins.

    Returns:
        DataFrame matching the trip profile schema, sorted by ``stop_sequence``.
        Empty (correct schema) if no data for this trip.
    """
    from multimodalmodel.benchmark import classify_predictions_by_stop

    meta = tracker.get_resolved_stops_df()
    meta = meta.filter(pl.col("trip_id") == trip_id)

    if meta.is_empty():
        return pl.DataFrame(schema=_PROFILE_SCHEMA)

    if trip_start_unix is None:
        trip_start_unix = float(meta["scheduled_unix"].min())

    # Per-stop accuracy counts (optionally filtered to selected bins)
    stop_acc = classify_predictions_by_stop(meta, selected_bins=selected_bins)

    # One row per stop: mean scheduled/actual unix across all predictions for that stop
    stop_times = (
        meta.group_by(["stop_id", "stop_sequence"])
        .agg([
            pl.col("scheduled_unix").mean(),
            pl.col("actual_unix").mean(),
        ])
        .with_columns([
            ((pl.col("scheduled_unix") - trip_start_unix) / 60).alias("scheduled_min"),
            ((pl.col("actual_unix") - trip_start_unix) / 60).alias("actual_min"),
        ])
    )

    profile = (
        stop_times
        .join(stop_acc, on=["stop_id", "stop_sequence"], how="left")
        .with_columns([
            pl.col("correct_count").fill_null(0),
            pl.col("incorrect_count").fill_null(0),
        ])
    )

    name_expr = (
        pl.col("stop_id").replace(stop_name_map, default=None)
        if stop_name_map
        else pl.col("stop_id")
    )
    profile = profile.with_columns(name_expr.alias("stop_name"))

    return profile.select(list(_PROFILE_SCHEMA.keys())).sort("stop_sequence")
