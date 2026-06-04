"""MBTA v3 REST API → polars DataFrames (same output schema as gtfs_rt.py)."""

import time
from datetime import datetime

import httpx
import polars as pl

MBTA_BASE_URL = "https://api-v3.mbta.com"

# MBTA string → GTFS-RT integer (what PredictionTracker expects)
_STATUS_MAP: dict[str, int] = {
    "INCOMING_AT": 0,
    "STOPPED_AT": 1,
    "IN_TRANSIT_TO": 2,
}

# Must match multimodalmodel.gtfs_rt schemas exactly
_TU_SCHEMA: dict[str, type] = {
    "trip_id": pl.String,
    "route_id": pl.String,
    "stop_sequence": pl.Int32,
    "stop_id": pl.String,
    "arrival_time": pl.Float64,
    "arrival_delay": pl.Int32,
    "snapshot_time": pl.Float64,
}

_VP_SCHEMA: dict[str, type] = {
    "trip_id": pl.String,
    "route_id": pl.String,
    "vehicle_id": pl.String,
    "stop_sequence": pl.Int32,
    "stop_id": pl.String,
    "current_status": pl.Int32,
    "timestamp": pl.Float64,
    "snapshot_time": pl.Float64,
}

# Well-known MBTA subway route IDs for UI dropdowns
MBTA_SUBWAY_ROUTES: dict[str, str] = {
    "Red Line": "Red",
    "Orange Line": "Orange",
    "Blue Line": "Blue",
    "Green Line B": "Green-B",
    "Green Line C": "Green-C",
    "Green Line D": "Green-D",
    "Green Line E": "Green-E",
    "Mattapan Trolley": "Mattapan",
}


def _iso_to_unix(ts: str | None) -> float | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts).timestamp()


def _get(endpoint: str, params: dict, api_key: str | None, timeout: int = 15) -> dict:
    headers = {"accept": "application/vnd.api+json"}
    if api_key:
        headers["x-api-key"] = api_key
    resp = httpx.get(
        f"{MBTA_BASE_URL}{endpoint}",
        params=params,
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json()


def _rel_id(relationships: dict, key: str) -> str:
    """Extract the ID from a JSON:API relationship object."""
    data = (relationships.get(key) or {}).get("data") or {}
    return data.get("id") or ""


def fetch_mbta_predictions(
    route_id: str | None = None,
    stop_id: str | None = None,
    api_key: str | None = None,
    snapshot_time: float | None = None,
) -> pl.DataFrame:
    """Fetch live predictions from MBTA v3 /predictions.

    Returns a DataFrame compatible with
    :func:`~multimodalmodel.gtfs_rt.parse_trip_updates` so it plugs directly
    into :class:`~multimodalmodel.live_tracker.PredictionTracker`.

    ``arrival_delay`` is 0 — the MBTA v3 API encodes real-time delay into
    ``arrival_time`` directly; the raw delta is not exposed in this endpoint.
    """
    now = snapshot_time if snapshot_time is not None else time.time()

    params: dict[str, str] = {}
    if route_id:
        params["filter[route]"] = route_id
    if stop_id:
        params["filter[stop]"] = stop_id

    body = _get("/predictions", params, api_key)

    rows: list[dict] = []
    for item in body.get("data", []):
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})

        arrival_ts = _iso_to_unix(attrs.get("arrival_time"))
        if arrival_ts is None or arrival_ts <= now:
            continue

        trip_id = _rel_id(rels, "trip")
        if not trip_id:
            continue

        rows.append({
            "trip_id": trip_id,
            "route_id": _rel_id(rels, "route"),
            "stop_sequence": int(attrs.get("stop_sequence") or 0),
            "stop_id": _rel_id(rels, "stop"),
            "arrival_time": arrival_ts,
            "arrival_delay": 0,
            "snapshot_time": now,
        })

    if not rows:
        return pl.DataFrame(schema=_TU_SCHEMA)
    return pl.DataFrame(rows, schema=_TU_SCHEMA)


def fetch_mbta_vehicles(
    route_id: str | None = None,
    api_key: str | None = None,
    snapshot_time: float | None = None,
) -> pl.DataFrame:
    """Fetch live vehicle positions from MBTA v3 /vehicles.

    Returns a DataFrame compatible with
    :func:`~multimodalmodel.gtfs_rt.parse_vehicle_positions`.
    """
    now = snapshot_time if snapshot_time is not None else time.time()

    params: dict[str, str] = {}
    if route_id:
        params["filter[route]"] = route_id

    body = _get("/vehicles", params, api_key)

    rows: list[dict] = []
    for item in body.get("data", []):
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})

        status_str = attrs.get("current_status") or "IN_TRANSIT_TO"
        rows.append({
            "trip_id": _rel_id(rels, "trip"),
            "route_id": _rel_id(rels, "route"),
            "vehicle_id": item.get("id", ""),
            "stop_sequence": int(attrs.get("current_stop_sequence") or 0),
            "stop_id": _rel_id(rels, "stop"),
            "current_status": _STATUS_MAP.get(status_str, 2),
            "timestamp": _iso_to_unix(attrs.get("updated_at")) or now,
            "snapshot_time": now,
        })

    if not rows:
        return pl.DataFrame(schema=_VP_SCHEMA)
    return pl.DataFrame(rows, schema=_VP_SCHEMA)
