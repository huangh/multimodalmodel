"""Fetch live MBTA v3 data and print diagnostic logs.

Usage:
    python demo_mbta.py [route_id]           # tries live API (needs key in env MBTA_API_KEY)
    python demo_mbta.py --simulate [route]   # realistic simulation (no key needed)
"""

import os
import random
import sys
import time
from datetime import datetime

import polars as pl

from multimodalmodel.benchmark import BIN_SPECS
from multimodalmodel.mbta import fetch_mbta_predictions, fetch_mbta_vehicles

STATUS_NAMES = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}

# ── Red Line southbound stop data (real MBTA IDs) ────────────────────────────
_RL_STOPS = [
    ("70061", "Alewife"),
    ("70063", "Davis"),
    ("70065", "Porter"),
    ("70067", "Harvard"),
    ("70069", "Central"),
    ("70071", "Kendall/MIT"),
    ("70073", "Charles/MGH"),
    ("70075", "Park St"),
    ("70077", "Downtown Crossing"),
    ("70079", "South Station"),
    ("70081", "Broadway"),
    ("70083", "Andrew"),
    ("70085", "JFK/UMass"),
    ("70087", "Savin Hill"),
    ("70089", "Fields Corner"),
    ("70091", "Shawmut"),
    ("70093", "Ashmont"),
]
# Segment travel times between consecutive stops (seconds, typical off-peak)
_RL_SEG_S = [120, 90, 90, 120, 90, 120, 150, 90, 90, 120, 90, 120, 150, 90, 90, 90]


def _simulate(route: str, now: float, n_trains: int = 9, seed: int = 0) -> tuple[list, list]:
    """Generate realistic MBTA-shaped predictions and vehicle rows."""
    rng = random.Random(seed or int(now) % 1000)
    predictions: list[dict] = []
    vehicles: list[dict] = []
    headway_s = 390  # ~6.5 min peak headway

    for i in range(n_trains):
        offset = i * headway_s + rng.gauss(0, 20)
        if offset < 0:
            offset = 0

        # Walk forward through segments to find current position
        cumulative = 0.0
        seg_idx = 0
        for j, seg in enumerate(_RL_SEG_S):
            if cumulative + seg > offset:
                seg_idx = j
                break
            cumulative += seg
        else:
            continue  # train past the terminus — skip

        stop_id, _ = _RL_STOPS[seg_idx]
        trip_id = f"canonical-{60547000 + i * 37}-Red-1-Weekday-01"
        vehicle_id = f"R-{rng.randint(0x44000000, 0x7FFFFFFF):08X}"

        vehicles.append({
            "vehicle_id": vehicle_id,
            "trip_id": trip_id,
            "route_id": route,
            "stop_id": stop_id,
            "stop_sequence": seg_idx + 1,
            "current_status": rng.choice([1, 2, 2, 2]),  # mostly IN_TRANSIT
            "timestamp": now - rng.uniform(5, 45),
        })

        time_to_next = (cumulative + _RL_SEG_S[seg_idx]) - offset
        running_s = time_to_next

        for seq in range(seg_idx, len(_RL_STOPS)):
            if running_s > 920:
                break
            sid, _ = _RL_STOPS[seq]
            arrival = now + running_s + rng.gauss(8, 18)  # slight positive bias (slightly late)
            predictions.append({
                "trip_id": trip_id,
                "route_id": route,
                "stop_id": sid,
                "stop_sequence": seq + 1,
                "arrival_time": arrival,
                "arrival_delay": 0,
                "snapshot_time": now,
            })
            if seq < len(_RL_SEG_S):
                running_s += _RL_SEG_S[seq] + rng.gauss(5, 12)

    return predictions, vehicles


def _print_predictions(tu_df: pl.DataFrame, now: float) -> None:
    upcoming = tu_df.sort("arrival_time").head(14)
    print(f"  {'trip_id':<44} {'stop_id':<8} {'wait':>7}  {'arrives'}")
    print(f"  {'-'*44} {'-'*8} {'-'*7}  {'-'*8}")
    for row in upcoming.iter_rows(named=True):
        wait_s = row["arrival_time"] - now
        arrives = datetime.fromtimestamp(row["arrival_time"]).strftime("%H:%M:%S")
        print(f"  {row['trip_id']:<44} {row['stop_id']:<8} {wait_s/60:>6.1f}m  {arrives}")
    print()

    print("  Prediction horizon distribution (IBI bins):")
    for spec in BIN_SPECS:
        count = len(tu_df.filter(
            (pl.col("arrival_time") - now >= spec["min_s"]) &
            (pl.col("arrival_time") - now < spec["max_s"])
        ))
        bar = "█" * min(count, 40)
        print(f"    {spec['label']:12}  {count:3}  {bar}")
    beyond = len(tu_df.filter((pl.col("arrival_time") - now) >= 900))
    print(f"    {'> 15 min':12}  {beyond:3}  (beyond IBI range)")
    print()


def _print_vehicles(vp_df: pl.DataFrame) -> None:
    print(f"  {'vehicle_id':<22} {'trip_id':<44} {'seq':>4}  status")
    print(f"  {'-'*22} {'-'*44} {'-'*4}  {'-'*13}")
    for row in vp_df.sort("vehicle_id").iter_rows(named=True):
        status = STATUS_NAMES.get(row["current_status"], "UNKNOWN")
        print(f"  {row['vehicle_id']:<22} {row['trip_id']:<44} {row['stop_sequence']:>4}  {status}")
    print()

    counts = vp_df.group_by("current_status").len().sort("current_status")
    print("  Status breakdown:")
    for row in counts.iter_rows(named=True):
        name = STATUS_NAMES.get(row["current_status"], "UNKNOWN")
        print(f"    {name:<14}  {row['len']}")
    print()


def main() -> None:
    args = sys.argv[1:]
    simulate = "--simulate" in args
    route_args = [a for a in args if a != "--simulate"]
    route = route_args[0] if route_args else "Red"
    api_key = os.environ.get("MBTA_API_KEY") or None

    print(f"{'=' * 64}")
    if simulate:
        print(f"  MBTA v3 API Demo  [SIMULATION]  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"  MBTA v3 API Demo  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Route: {route}{'  (API key: set)' if api_key else '  (no API key)'}")
    print(f"{'=' * 64}\n")

    now = time.time()

    if simulate:
        print("[SIM] Generating realistic MBTA Red Line data ...\n")
        pred_rows, veh_rows = _simulate(route, now)
        tu_df = pl.DataFrame(pred_rows, schema={
            "trip_id": pl.String, "route_id": pl.String, "stop_id": pl.String,
            "stop_sequence": pl.Int32, "arrival_time": pl.Float64,
            "arrival_delay": pl.Int32, "snapshot_time": pl.Float64,
        }) if pred_rows else pl.DataFrame(schema={
            "trip_id": pl.String, "route_id": pl.String, "stop_sequence": pl.Int32,
            "stop_id": pl.String, "arrival_time": pl.Float64, "arrival_delay": pl.Int32,
            "snapshot_time": pl.Float64,
        })
        vp_df = pl.DataFrame(veh_rows, schema={
            "vehicle_id": pl.String, "trip_id": pl.String, "route_id": pl.String,
            "stop_id": pl.String, "stop_sequence": pl.Int32, "current_status": pl.Int32,
            "timestamp": pl.Float64, "snapshot_time": pl.Float64,
        }) if veh_rows else pl.DataFrame(schema={
            "trip_id": pl.String, "route_id": pl.String, "vehicle_id": pl.String,
            "stop_sequence": pl.Int32, "stop_id": pl.String, "current_status": pl.Int32,
            "timestamp": pl.Float64, "snapshot_time": pl.Float64,
        })
        print(f"[1/2] Predictions: {len(tu_df)} future stop predictions\n")
        _print_predictions(tu_df, now)
        print(f"[2/2] Vehicles: {len(vp_df)} active vehicles\n")
        _print_vehicles(vp_df)
    else:
        print("[1/2] GET /predictions ...")
        t0 = time.perf_counter()
        tu_df = fetch_mbta_predictions(route_id=route, api_key=api_key, snapshot_time=now)
        ms = (time.perf_counter() - t0) * 1000
        print(f"      {len(tu_df)} future stop predictions  ({ms:.0f} ms)\n")
        if tu_df.is_empty():
            print("      (No predictions returned — service may not be running.)\n")
        else:
            _print_predictions(tu_df, now)

        print("[2/2] GET /vehicles ...")
        t0 = time.perf_counter()
        vp_df = fetch_mbta_vehicles(route_id=route, api_key=api_key, snapshot_time=now)
        ms = (time.perf_counter() - t0) * 1000
        print(f"      {len(vp_df)} active vehicles  ({ms:.0f} ms)\n")
        if vp_df.is_empty():
            print("      (No vehicles returned.)\n")
        else:
            _print_vehicles(vp_df)

    print(f"Done.  {len(tu_df)} predictions · {len(vp_df)} vehicles")


if __name__ == "__main__":
    main()
