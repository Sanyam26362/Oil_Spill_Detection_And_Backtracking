from __future__ import annotations

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# PROJECT ROOT
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------------------------

import asyncio
import json

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

COAST_DIR = PROJECT_ROOT / "json_output" / "coast"
WATER_DIR = PROJECT_ROOT / "json_output" / "water"


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

NUM_DETECTIONS = 5

ENSEMBLE_SIZE = 100
INITIAL_RADIUS_M = 500.0
TIMESTEP_MINUTES = 15
CANDIDATE_RADIUS_MARGIN_KM = 5.0
CANDIDATE_TIME_WINDOW_HOURS = 2.0


# ---------------------------------------------------------------------------
# LOAD DETECTIONS
# ---------------------------------------------------------------------------

def load_detections():

    detections = []

    sources = [
        ("coast", COAST_DIR, "oc-*.json"),
        ("water", WATER_DIR, "ow-*.json"),
    ]

    for source_type, directory, pattern in sources:

        files = sorted(directory.glob(pattern))

        for file_path in files:

            try:

                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                ) as f:
                    data = json.load(f)

                for detection in data.get(
                    "detections",
                    [],
                ):

                    detection["_source_type"] = (
                        source_type
                    )

                    detection["_source_file"] = (
                        file_path.name
                    )

                    detections.append(detection)

            except Exception as exc:

                print(
                    f"ERROR reading {file_path}: {exc}"
                )

    return detections


# ---------------------------------------------------------------------------
# DATETIME
# ---------------------------------------------------------------------------

def parse_datetime(value: str) -> datetime:

    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# DATABASE DIAGNOSTICS
# ---------------------------------------------------------------------------

async def database_diagnostics(
    db,
    latitude,
    longitude,
    start_time,
    end_time,
    radius_km,
):

    print()
    print("AIS DATABASE CHECK")
    print("-" * 80)

    print(
        f"Search latitude  : {latitude:.8f}"
    )

    print(
        f"Search longitude : {longitude:.8f}"
    )

    print(
        f"Search radius    : {radius_km:.6f} km"
    )

    print(
        f"Search start     : {start_time.isoformat()}"
    )

    print(
        f"Search end       : {end_time.isoformat()}"
    )

    # -----------------------------------------------------------------------
    # 1. Check AIS records in time window
    # -----------------------------------------------------------------------

    result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) AS records,
                COUNT(DISTINCT vessel_id) AS vessels
            FROM ais_positions
            WHERE is_synthetic = TRUE
              AND timestamp >= :start_time
              AND timestamp <= :end_time
            """
        ),
        {
            "start_time": start_time,
            "end_time": end_time,
        },
    )

    row = result.one()

    print()
    print(
        f"AIS records in time window : "
        f"{row.records:,}"
    )

    print(
        f"Vessels in time window     : "
        f"{row.vessels:,}"
    )

    # -----------------------------------------------------------------------
    # 2. Check spatial candidates
    # -----------------------------------------------------------------------

    radius_m = radius_km * 1000.0

    result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) AS records,
                COUNT(DISTINCT vessel_id) AS vessels
            FROM ais_positions
            WHERE is_synthetic = TRUE
              AND timestamp >= :start_time
              AND timestamp <= :end_time
              AND ST_DWithin(
                    geometry::geography,
                    ST_SetSRID(
                        ST_MakePoint(
                            :longitude,
                            :latitude
                        ),
                        4326
                    )::geography,
                    :radius_m
              )
            """
        ),
        {
            "start_time": start_time,
            "end_time": end_time,
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": radius_m,
        },
    )

    row = result.one()

    print()
    print(
        f"AIS records spatially near source : "
        f"{row.records:,}"
    )

    print(
        f"Vessels spatially near source     : "
        f"{row.vessels:,}"
    )

    # -----------------------------------------------------------------------
    # 3. Nearest synthetic AIS record
    # -----------------------------------------------------------------------

    result = await db.execute(
        text(
            """
            SELECT
                vessel_id,
                timestamp,
                latitude,
                longitude,
                ST_Distance(
                    geometry::geography,
                    ST_SetSRID(
                        ST_MakePoint(
                            :longitude,
                            :latitude
                        ),
                        4326
                    )::geography
                ) / 1000.0 AS distance_km
            FROM ais_positions
            WHERE is_synthetic = TRUE
              AND timestamp >= :start_time
              AND timestamp <= :end_time
            ORDER BY
                geometry::geography <->
                ST_SetSRID(
                    ST_MakePoint(
                        :longitude,
                        :latitude
                    ),
                    4326
                )::geography
            LIMIT 5
            """
        ),
        {
            "start_time": start_time,
            "end_time": end_time,
            "latitude": latitude,
            "longitude": longitude,
        },
    )

    rows = result.fetchall()

    print()
    print("NEAREST AIS RECORDS")
    print("-" * 80)

    if not rows:

        print("No synthetic AIS records found.")

    else:

        for row in rows:

            print(
                f"{row.vessel_id:<25} "
                f"{row.timestamp} "
                f"distance={row.distance_km:.4f} km"
            )


# ---------------------------------------------------------------------------
# MAIN DIAGNOSTIC
# ---------------------------------------------------------------------------

async def main():

    print("=" * 90)
    print("DETECTION ATTRIBUTION DIAGNOSTIC")
    print("=" * 90)

    detections = load_detections()

    print()
    print(
        f"Loaded detections : {len(detections):,}"
    )

    print(
        f"Testing first     : {NUM_DETECTIONS}"
    )

    # -----------------------------------------------------------------------
    # WEATHER SERVICE
    # -----------------------------------------------------------------------

    weather_service = WeatherService(
        weather_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "weather"
            / "raw"
            / "yearly"
        ),
        ocean_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "ocean"
            / "raw"
            / "yearly"
        ),
    )

    engine = AttributionEngine(
        weather_service=weather_service
    )

    try:

        async with AsyncSessionLocal() as db:

            for index, detection in enumerate(
                detections[:NUM_DETECTIONS],
                start=1,
            ):

                print()
                print()
                print("=" * 90)
                print(
                    f"DETECTION {index}/{NUM_DETECTIONS}"
                )
                print("=" * 90)

                spill_id = detection.get(
                    "spill_id"
                )

                source_type = detection.get(
                    "_source_type"
                )

                source_file = detection.get(
                    "_source_file"
                )

                latitude = float(
                    detection["centroid"]["lat"]
                )

                longitude = float(
                    detection["centroid"]["lon"]
                )

                detected_at = parse_datetime(
                    detection["detected_at"]
                )

                age_hours = float(
                    detection["estimated_age_hours"]
                )

                release_time = (
                    detected_at
                    - timedelta(
                        hours=age_hours
                    )
                )

                print()
                print("DETECTION INPUT")
                print("-" * 80)

                print(
                    f"Spill ID          : {spill_id}"
                )

                print(
                    f"Source type       : {source_type}"
                )

                print(
                    f"Source file       : {source_file}"
                )

                print(
                    f"Observation lat   : {latitude:.8f}"
                )

                print(
                    f"Observation lon   : {longitude:.8f}"
                )

                print(
                    f"Detected at       : "
                    f"{detected_at.isoformat()}"
                )

                print(
                    f"Estimated age     : "
                    f"{age_hours:.2f} hours"
                )

                print(
                    f"Estimated release : "
                    f"{release_time.isoformat()}"
                )

                # ----------------------------------------------------------------
                # AIS CHECK AROUND THE DETECTION POSITION
                #
                # This tells us whether AIS exists around the observation itself.
                # ----------------------------------------------------------------

                observation_start = (
                    detected_at
                    - timedelta(
                        hours=2
                    )
                )

                observation_end = (
                    detected_at
                    + timedelta(
                        hours=2
                    )
                )

                await database_diagnostics(
                    db=db,
                    latitude=latitude,
                    longitude=longitude,
                    start_time=observation_start,
                    end_time=observation_end,
                    radius_km=10.0,
                )

                # ----------------------------------------------------------------
                # RUN ATTRIBUTION
                # ----------------------------------------------------------------

                print()
                print("RUNNING HINDCAST + ATTRIBUTION")
                print("-" * 80)

                started = time.perf_counter()

                try:

                    result = await engine.attribute(
                        db=db,

                        observation_latitude=latitude,
                        observation_longitude=longitude,

                        observation_time=detected_at,

                        drift_duration_hours=age_hours,

                        ensemble_size=ENSEMBLE_SIZE,
                        initial_radius_m=INITIAL_RADIUS_M,
                        timestep_minutes=TIMESTEP_MINUTES,

                        candidate_radius_margin_km=(
                            CANDIDATE_RADIUS_MARGIN_KM
                        ),

                        candidate_time_window_hours=(
                            CANDIDATE_TIME_WINDOW_HOURS
                        ),

                        synthetic_only=True,
                        scenario_id=None,
                    )

                    elapsed = (
                        time.perf_counter()
                        - started
                    )

                    # ------------------------------------------------------------
                    # SOURCE ESTIMATE
                    # ------------------------------------------------------------

                    source_estimate = result.get(
                        "source_estimate",
                        {},
                    )

                    source_lat = source_estimate.get(
                        "latitude"
                    )

                    source_lon = source_estimate.get(
                        "longitude"
                    )

                    radius_km = source_estimate.get(
                        "radius_km"
                    )

                    print()
                    print("HINDCAST SOURCE ESTIMATE")
                    print("-" * 80)

                    print(
                        f"Latitude  : {source_lat}"
                    )

                    print(
                        f"Longitude : {source_lon}"
                    )

                    print(
                        f"Radius    : {radius_km} km"
                    )

                    # ------------------------------------------------------------
                    # EXPECTED CANDIDATE SEARCH WINDOW
                    # ------------------------------------------------------------

                    search_radius_km = max(
                        float(radius_km)
                        + CANDIDATE_RADIUS_MARGIN_KM,
                        1.0,
                    )

                    search_start = (
                        release_time
                        - timedelta(
                            hours=CANDIDATE_TIME_WINDOW_HOURS
                        )
                    )

                    search_end = (
                        release_time
                        + timedelta(
                            hours=CANDIDATE_TIME_WINDOW_HOURS
                        )
                    )

                    print()
                    print(
                        "ACTUAL CANDIDATE SEARCH WINDOW"
                    )
                    print("-" * 80)

                    print(
                        f"Latitude       : "
                        f"{source_lat}"
                    )

                    print(
                        f"Longitude      : "
                        f"{source_lon}"
                    )

                    print(
                        f"Radius         : "
                        f"{search_radius_km:.6f} km"
                    )

                    print(
                        f"Start          : "
                        f"{search_start.isoformat()}"
                    )

                    print(
                        f"End            : "
                        f"{search_end.isoformat()}"
                    )

                    # ------------------------------------------------------------
                    # DIRECT DB CHECK AT HINDCAST SOURCE
                    # ------------------------------------------------------------

                    await database_diagnostics(
                        db=db,
                        latitude=float(source_lat),
                        longitude=float(source_lon),
                        start_time=search_start,
                        end_time=search_end,
                        radius_km=search_radius_km,
                    )

                    # ------------------------------------------------------------
                    # ATTRIBUTION RESULT
                    # ------------------------------------------------------------

                    candidates = result.get(
                        "candidates",
                        [],
                    )

                    print()
                    print("ATTRIBUTION RESULT")
                    print("-" * 80)

                    print(
                        f"Candidate count : "
                        f"{result.get('candidate_count')}"
                    )

                    print(
                        f"Top prediction  : "
                        f"{result.get('top_prediction')}"
                    )

                    print(
                        f"Ranked vessels  : "
                        f"{len(candidates)}"
                    )

                    if candidates:

                        print()
                        print(
                            "TOP CANDIDATES"
                        )

                        for rank, candidate in enumerate(
                            candidates[:10],
                            start=1,
                        ):

                            print(
                                f"{rank:2}. "
                                f"{candidate.get('vessel_id')} "
                                f"score="
                                f"{candidate.get('total_score')}"
                            )

                    print()
                    print(
                        f"TOTAL RUNTIME : "
                        f"{elapsed:.2f} seconds"
                    )

                except Exception as exc:

                    elapsed = (
                        time.perf_counter()
                        - started
                    )

                    print()
                    print(
                        "ATTRIBUTION FAILED"
                    )

                    print(
                        f"Error   : {exc}"
                    )

                    print(
                        f"Runtime : "
                        f"{elapsed:.2f} seconds"
                    )

    finally:

        weather_service.close()

    print()
    print("=" * 90)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())