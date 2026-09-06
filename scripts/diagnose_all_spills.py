#!/usr/bin/env python3
"""
Comprehensive Diagnostic Tool: Backtracking & AIS Coverage Audit
Evaluates all detections against PostgreSQL/PostGIS without modifying any state.
"""

import asyncio
import csv
import logging
import math
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg

# Database Configuration
DB_CONFIG = {
    "user": "sih_admin",
    "password": "sih_password",  # adjust to match local env
    "database": "oil_spill_db",
    "host": "localhost",
    "port": 5432,
}

OUTPUT_CSV = "spill_ais_diagnostic_report.csv"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("diagnostic")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * R * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


QUERY_AIS_RING_METRICS = """
WITH origin_point AS (
    SELECT ST_SetSRID(ST_Point($1, $2), 4326)::geography AS geog
),
filtered_pings AS (
    SELECT 
        vessel_id,
        timestamp,
        geom,
        ST_Distance(geom, (SELECT geog FROM origin_point)) AS dist_m
    FROM ais_positions
    WHERE timestamp BETWEEN $3 AND $4
      AND ST_DWithin(geom, (SELECT geog FROM origin_point), $5)
)
SELECT 
    COUNT(*) AS ping_count,
    COUNT(DISTINCT vessel_id) AS vessel_count,
    MIN(dist_m) AS min_dist_m
FROM filtered_pings;
"""

QUERY_CLOSEST_VESSEL = """
WITH origin_point AS (
    SELECT ST_SetSRID(ST_Point($1, $2), 4326)::geography AS geog
)
SELECT 
    vessel_id,
    timestamp,
    scenario_id,
    is_synthetic,
    ST_Distance(geom, (SELECT geog FROM origin_point)) / 1000.0 AS dist_km
FROM ais_positions
WHERE timestamp BETWEEN $3 AND $4
  AND ST_DWithin(geom, (SELECT geog FROM origin_point), 50000)
ORDER BY dist_km ASC
LIMIT 1;
"""


async def run_diagnostics():
    logger.info("Connecting to database...")
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)

    # 1. Fetch Detections
    logger.info("Fetching detections from database...")
    spills = await conn.fetch("""
        SELECT 
            spill_id, 
            detection_timestamp, 
            ST_Y(geom::geometry) AS obs_lat, 
            ST_X(geom::geometry) AS obs_lon,
            COALESCE(estimated_age_hours, 12.0) AS age_hours
        FROM spills
        ORDER BY detection_timestamp ASC;
    """)
    logger.info(f"Loaded {len(spills)} spill detections.")

    results: List[Dict[str, Any]] = []

    for idx, row in enumerate(spills):
        spill_id = row["spill_id"]
        obs_time: datetime = row["detection_timestamp"]
        obs_lat: float = row["obs_lat"]
        obs_lon: float = row["obs_lon"]
        age_hours: float = float(row["age_hours"])

        # Time conversions
        release_time = obs_time - timedelta(hours=age_hours)
        win_rel_start = release_time - timedelta(hours=2)
        win_rel_end = release_time + timedelta(hours=2)
        win_obs_start = obs_time - timedelta(hours=2)
        win_obs_end = obs_time + timedelta(hours=2)
        win_exact_start = release_time - timedelta(minutes=15)
        win_exact_end = release_time + timedelta(minutes=15)

        # Baseline: simulate or load backtrack coordinates
        # Note: If backtracked coordinates are persisted, fetch them from attribution table.
        # Otherwise, compute displacement vector or query live engine.
        backtrack_row = await conn.fetchrow("""
            SELECT 
                ST_Y(source_geom::geometry) AS src_lat,
                ST_X(source_geom::geometry) AS src_lon,
                source_radius_km
            FROM spill_backtrack_results
            WHERE spill_id = $1
            LIMIT 1;
        """, spill_id)

        if backtrack_row and backtrack_row["src_lat"] is not None:
            src_lat = float(backtrack_row["src_lat"])
            src_lon = float(backtrack_row["src_lon"])
            src_radius = float(backtrack_row["source_radius_km"])
        else:
            # Fallback placeholder to observation location if not backtracked
            src_lat, src_lon, src_radius = obs_lat, obs_lon, 5.0

        # Mirror/Inverted point (testing flipped direction vector)
        mirror_lat = obs_lat - (src_lat - obs_lat)
        mirror_lon = obs_lon - (src_lon - obs_lon)

        record = {
            "spill_id": spill_id,
            "obs_time": obs_time.isoformat(),
            "obs_lat": obs_lat,
            "obs_lon": obs_lon,
            "age_hours": age_hours,
            "release_time": release_time.isoformat(),
            "backtrack_lat": src_lat,
            "backtrack_lon": src_lon,
            "source_radius_km": src_radius,
            "drift_distance_km": round(haversine_km(obs_lat, obs_lon, src_lat, src_lon), 3),
        }

        # Multi-ring tests at Backtrack Origin (±2h)
        for r_m, label in [(5000, "5km"), (10000, "10km"), (25000, "25km"), (50000, "50km")]:
            res = await conn.fetchrow(
                QUERY_AIS_RING_METRICS, src_lon, src_lat, win_rel_start, win_rel_end, float(r_m)
            )
            record[f"src_rel2h_pings_{label}"] = res["ping_count"]
            record[f"src_rel2h_vessels_{label}"] = res["vessel_count"]

        # Exact release time ring (±15 min at 10 km)
        exact_res = await conn.fetchrow(
            QUERY_AIS_RING_METRICS, src_lon, src_lat, win_exact_start, win_exact_end, 10000.0
        )
        record["src_exact15m_vessels_10km"] = exact_res["vessel_count"]

        # Observation point ring (±2h at 10 km)
        obs_res = await conn.fetchrow(
            QUERY_AIS_RING_METRICS, obs_lon, obs_lat, win_obs_start, win_obs_end, 10000.0
        )
        record["obs_win2h_vessels_10km"] = obs_res["vessel_count"]

        # Mirror point ring (±2h at 10 km)
        mirror_res = await conn.fetchrow(
            QUERY_AIS_RING_METRICS, mirror_lon, mirror_lat, win_rel_start, win_rel_end, 10000.0
        )
        record["mirror_rel2h_vessels_10km"] = mirror_res["vessel_count"]

        # Closest vessel details
        closest = await conn.fetchrow(
            QUERY_CLOSEST_VESSEL, src_lon, src_lat, win_rel_start, win_rel_end
        )
        if closest:
            record["closest_vessel_id"] = closest["vessel_id"]
            record["closest_vessel_dist_km"] = round(float(closest["dist_km"]), 3)
            record["closest_vessel_time"] = closest["timestamp"].isoformat()
            record["closest_is_synthetic"] = closest["is_synthetic"]
            record["closest_scenario_id"] = closest["scenario_id"]
        else:
            record["closest_vessel_id"] = None
            record["closest_vessel_dist_km"] = None
            record["closest_vessel_time"] = None
            record["closest_is_synthetic"] = None
            record["closest_scenario_id"] = None

        results.append(record)

        if (idx + 1) % 100 == 0 or (idx + 1) == len(spills):
            logger.info(f"Processed {idx + 1}/{len(spills)} detections...")

    await conn.close()

    # Write Results to CSV
    if results:
        fieldnames = list(results[0].keys())
        with open(OUTPUT_CSV, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"Diagnostic report written successfully to {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(run_diagnostics())