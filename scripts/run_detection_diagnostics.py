#!/usr/bin/env python3
import asyncio
import csv
import glob
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.audit_spill_jsons import parse_spill_file

try:
    from app.core.config import settings
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(raw_url)
    DB_CONFIG = {
        "user": parsed.username or "sih_admin",
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
    }
except Exception:
    DB_CONFIG = {
        "user": os.getenv("POSTGRES_USER", "sih_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "sih_secure_password_2026"),
        "database": os.getenv("POSTGRES_DB", "oil_spill_db"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
    }

VALIDATION_CSV = os.path.join("json_output", "validation", "detection_attribution_results.csv")
OUTPUT_CSV = "detection_diagnostic_report.csv"
CONCURRENCY = 4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("diagnostic")

KM_TO_DEG_LAT = 1.0 / 110.9
KM_TO_DEG_LON = 1.0 / 91.2

QUERY_BACKTRACK_RINGS = """
WITH origin AS (
    SELECT ST_SetSRID(ST_Point($1, $2), 4326) AS geom_pt
),
filtered AS (
    SELECT 
        vessel_id,
        timestamp,
        scenario_id,
        geometry,
        ST_Distance(geometry, (SELECT geom_pt FROM origin)) AS dist_deg
    FROM ais_positions
    WHERE timestamp BETWEEN $3 AND $4
      AND latitude BETWEEN $2 - ($5 * 1.05) AND $2 + ($5 * 1.05)
      AND longitude BETWEEN $1 - ($6 * 1.05) AND $1 + ($6 * 1.05)
      AND ST_DWithin(geometry, (SELECT geom_pt FROM origin), $7)
)
SELECT 
    COUNT(*) AS pings_50km,
    COUNT(DISTINCT vessel_id) AS vessels_50km,
    COUNT(*) FILTER (WHERE dist_deg <= $8) AS pings_25km,
    COUNT(DISTINCT vessel_id) FILTER (WHERE dist_deg <= $8) AS vessels_25km,
    COUNT(*) FILTER (WHERE dist_deg <= $9) AS pings_10km,
    COUNT(DISTINCT vessel_id) FILTER (WHERE dist_deg <= $9) AS vessels_10km,
    COUNT(*) FILTER (WHERE dist_deg <= $10) AS pings_5km,
    COUNT(DISTINCT vessel_id) FILTER (WHERE dist_deg <= $10) AS vessels_5km,
    COUNT(DISTINCT vessel_id) FILTER (WHERE timestamp BETWEEN $11 AND $12 AND dist_deg <= $9) AS vessels_exact15m_10km,
    MIN(dist_deg) AS min_dist_deg
FROM filtered;
"""

QUERY_CLOSEST_VESSEL = """
WITH origin AS (
    SELECT ST_SetSRID(ST_Point($1, $2), 4326) AS geom_pt
)
SELECT 
    vessel_id,
    timestamp,
    scenario_id,
    is_synthetic,
    ROUND((ST_Distance(geometry::geography, (SELECT geom_pt::geography FROM origin)) / 1000.0)::numeric, 3) AS dist_km
FROM ais_positions
WHERE timestamp BETWEEN $3 AND $4
  AND latitude BETWEEN $2 - 0.50 AND $2 + 0.50
  AND longitude BETWEEN $1 - 0.60 AND $1 + 0.60
ORDER BY geometry <-> (SELECT geom_pt FROM origin)
LIMIT 1;
"""


def load_known_backtrack():
    mapping = {}
    if not os.path.exists(VALIDATION_CSV):
        logger.warning(f"Validation CSV not found at {VALIDATION_CSV}")
        return mapping

    with open(VALIDATION_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sid = r.get("spill_id")
            lat = r.get("estimated_source_latitude")
            lon = r.get("estimated_source_longitude")
            rad = r.get("estimated_source_radius_km") or 5.0
            orig_cnt = r.get("candidate_count") or 0
            top_v = r.get("ranked_top_vessel") or r.get("top_prediction") or ""
            rel_t = r.get("estimated_release_time")

            if sid and lat and lon:
                mapping[sid] = {
                    "src_lat": float(lat),
                    "src_lon": float(lon),
                    "source_radius_km": float(rad) if float(rad) > 0.0 else 5.0,
                    "original_candidate_count": int(orig_cnt),
                    "original_top_vessel": top_v,
                    "csv_release_time": rel_t,
                }
    logger.info(f"Loaded {len(mapping)} records from {VALIDATION_CSV}")
    return mapping


async def process_spill(sem, pool, s, known_bt, total, results):
    async with sem:
        obs_time = s["obs_time"]
        obs_lat, obs_lon = s["lat"], s["lon"]
        age_hours = s["age_hours"]

        bt_info = known_bt.get(s["spill_id"])
        if bt_info:
            src_lat = bt_info["src_lat"]
            src_lon = bt_info["src_lon"]
            src_radius = bt_info["source_radius_km"]
            orig_count = bt_info["original_candidate_count"]
            orig_vessel = bt_info["original_top_vessel"]
            has_backtrack = True
            if bt_info["csv_release_time"]:
                try:
                    release_time = datetime.fromisoformat(bt_info["csv_release_time"].replace("Z", "+00:00"))
                except Exception:
                    release_time = obs_time - timedelta(hours=age_hours)
            else:
                release_time = obs_time - timedelta(hours=age_hours)
        else:
            src_lat, src_lon, src_radius = obs_lat, obs_lon, 5.0
            orig_count = 0
            orig_vessel = ""
            has_backtrack = False
            release_time = obs_time - timedelta(hours=age_hours)

        deg_50k_lat = 50.0 * KM_TO_DEG_LAT
        deg_50k_lon = 50.0 * KM_TO_DEG_LON
        deg_50k = math.sqrt((50.0 * KM_TO_DEG_LAT) ** 2 + (50.0 * KM_TO_DEG_LON) ** 2)
        deg_25k = math.sqrt((25.0 * KM_TO_DEG_LAT) ** 2 + (25.0 * KM_TO_DEG_LON) ** 2)
        deg_10k = math.sqrt((10.0 * KM_TO_DEG_LAT) ** 2 + (10.0 * KM_TO_DEG_LON) ** 2)
        deg_5k = math.sqrt((5.0 * KM_TO_DEG_LAT) ** 2 + (5.0 * KM_TO_DEG_LON) ** 2)

        w_start, w_end = release_time - timedelta(hours=2), release_time + timedelta(hours=2)
        exact_start, exact_end = release_time - timedelta(minutes=15), release_time + timedelta(minutes=15)

        async with pool.acquire() as conn:
            bt_metrics = await conn.fetchrow(
                QUERY_BACKTRACK_RINGS,
                src_lon, src_lat,
                w_start, w_end,
                deg_50k_lat, deg_50k_lon, deg_50k,
                deg_25k, deg_10k, deg_5k,
                exact_start, exact_end,
            )

            closest = await conn.fetchrow(
                QUERY_CLOSEST_VESSEL,
                src_lon, src_lat,
                w_start, w_end,
            )

        min_dist_km = (
            round(float(bt_metrics["min_dist_deg"]) * 100.0, 2)
            if bt_metrics["min_dist_deg"] is not None
            else None
        )

        record = {
            "spill_id": s["spill_id"],
            "obs_time": obs_time.isoformat(),
            "obs_lat": obs_lat,
            "obs_lon": obs_lon,
            "age_hours": age_hours,
            "release_time": release_time.isoformat(),
            "release_in_2018": release_time.year < 2019,
            "has_backtrack": has_backtrack,
            "src_lat": src_lat,
            "src_lon": src_lon,
            "source_radius_km": src_radius,
            "original_candidate_count": orig_count,
            "original_top_vessel": orig_vessel,
            "vessels_5km": bt_metrics["vessels_5km"],
            "pings_5km": bt_metrics["pings_5km"],
            "vessels_10km": bt_metrics["vessels_10km"],
            "pings_10km": bt_metrics["pings_10km"],
            "vessels_25km": bt_metrics["vessels_25km"],
            "vessels_50km": bt_metrics["vessels_50km"],
            "vessels_exact15m_10km": bt_metrics["vessels_exact15m_10km"],
            "min_dist_km": min_dist_km,
            "closest_vessel_id": closest["vessel_id"] if closest else None,
            "closest_dist_km": float(closest["dist_km"]) if closest else None,
            "closest_timestamp": closest["timestamp"].isoformat() if closest else None,
            "closest_scenario_id": closest["scenario_id"] if closest else None,
            "closest_is_synthetic": closest["is_synthetic"] if closest else None,
        }
        results.append(record)

        if len(results) % 100 == 0 or len(results) == total:
            logger.info(f"Progress: {len(results)}/{total} spills evaluated ({len(results)/total*100:.1f}%)")


async def main():
    files = glob.glob(os.path.join("json_output", "coast", "*.json")) + \
            glob.glob(os.path.join("json_output", "water", "*.json"))

    all_spills = []
    for f in files:
        all_spills.extend(parse_spill_file(f))

    spills = [s for s in all_spills if s["obs_time"] and s["lat"] is not None and s["lon"] is not None]
    total = len(spills)
    logger.info(f"Loaded {total} valid detections from {len(files)} files.")

    known_bt = load_known_backtrack()

    t0 = time.time()
    pool = await asyncpg.create_pool(min_size=CONCURRENCY, max_size=CONCURRENCY, **DB_CONFIG)
    sem = asyncio.Semaphore(CONCURRENCY)
    results = []

    tasks = [
        process_spill(sem, pool, s, known_bt, total, results)
        for s in spills
    ]
    await asyncio.gather(*tasks)
    await pool.close()

    elapsed = time.time() - t0
    logger.info(f"All {total} detections evaluated in {elapsed:.1f}s ({elapsed/total*1000:.1f} ms/spill).")

    results.sort(key=lambda r: r["obs_time"])

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    logger.info(f"Diagnostic report written to {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())