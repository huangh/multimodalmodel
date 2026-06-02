"""GTFS-RT feed fetching and protobuf → polars parsing."""

import httpx
import polars as pl
from google.transit import gtfs_realtime_pb2

_VP_SCHEMA = {
    "trip_id": pl.String,
    "route_id": pl.String,
    "vehicle_id": pl.String,
    "stop_sequence": pl.Int32,
    "stop_id": pl.String,
    "current_status": pl.Int32,
    "timestamp": pl.Float64,
    "snapshot_time": pl.Float64,
}

_TU_SCHEMA = {
    "trip_id": pl.String,
    "route_id": pl.String,
    "stop_sequence": pl.Int32,
    "stop_id": pl.String,
    "arrival_time": pl.Float64,
    "arrival_delay": pl.Int32,
    "snapshot_time": pl.Float64,
}


def fetch_feed(url: str, headers: dict | None = None, timeout: int = 10) -> bytes:
    """Fetch a GTFS-RT binary protobuf feed over HTTP.

    Raises ``httpx.HTTPError`` on non-2xx responses or network failures.
    """
    response = httpx.get(url, headers=headers or {}, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.content


def parse_vehicle_positions(feed_bytes: bytes, snapshot_time: float) -> pl.DataFrame:
    """Parse a GTFS-RT feed and return all VehiclePosition entities.

    Args:
        feed_bytes: Raw protobuf bytes from a GTFS-RT feed.
        snapshot_time: Unix timestamp of when the feed was fetched.

    Returns:
        DataFrame with columns matching ``_VP_SCHEMA``.
        ``current_status``: 0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT_TO.
        Empty (correct schema) if no vehicle entities are present.
    """
    if not feed_bytes:
        return pl.DataFrame(schema=_VP_SCHEMA)

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_bytes)

    rows = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vp = entity.vehicle
        rows.append({
            "trip_id": vp.trip.trip_id,
            "route_id": vp.trip.route_id,
            "vehicle_id": vp.vehicle.id,
            "stop_sequence": vp.current_stop_sequence,
            "stop_id": vp.stop_id,
            "current_status": int(vp.current_status),
            "timestamp": float(vp.timestamp) if vp.timestamp else snapshot_time,
            "snapshot_time": snapshot_time,
        })

    if not rows:
        return pl.DataFrame(schema=_VP_SCHEMA)
    return pl.DataFrame(rows, schema=_VP_SCHEMA)


def parse_trip_updates(feed_bytes: bytes, snapshot_time: float) -> pl.DataFrame:
    """Parse a GTFS-RT feed and return all StopTimeUpdate entries from TripUpdate entities.

    Args:
        feed_bytes: Raw protobuf bytes from a GTFS-RT feed.
        snapshot_time: Unix timestamp of when the feed was fetched.

    Returns:
        DataFrame with one row per (trip, stop) prediction, schema ``_TU_SCHEMA``.
        Rows where ``arrival_time == 0`` (no prediction) are excluded.
        Empty (correct schema) if no trip update entities are present.
    """
    if not feed_bytes:
        return pl.DataFrame(schema=_TU_SCHEMA)

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_bytes)

    rows = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        route_id = tu.trip.route_id
        for stu in tu.stop_time_update:
            if not stu.HasField("arrival"):
                continue
            arrival_time = float(stu.arrival.time)
            if arrival_time == 0:
                continue
            rows.append({
                "trip_id": trip_id,
                "route_id": route_id,
                "stop_sequence": stu.stop_sequence,
                "stop_id": stu.stop_id,
                "arrival_time": arrival_time,
                "arrival_delay": stu.arrival.delay,
                "snapshot_time": snapshot_time,
            })

    if not rows:
        return pl.DataFrame(schema=_TU_SCHEMA)
    return pl.DataFrame(rows, schema=_TU_SCHEMA)
