import asyncio
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService

if hasattr(database, "AsyncSessionLocal"):
    SessionLocal = database.AsyncSessionLocal
elif hasattr(database, "async_session"):
    SessionLocal = database.async_session
elif hasattr(database, "engine"):
    SessionLocal = async_sessionmaker(database.engine, class_=AsyncSession, expire_on_commit=False)


async def debug():
    # 1. Inspect diagnostic CSV record for spill_497182
    print("=== 1. DIAGNOSTIC REPORT VALUES ===")
    diag_row = None
    with open("detection_diagnostic_report.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["spill_id"] == "spill_497182":
                diag_row = r
                break

    if diag_row:
        print(f"  Observed Point:     ({diag_row['obs_lat']}, {diag_row['obs_lon']})")
        print(f"  CSV Source Point:   ({diag_row['src_lat']}, {diag_row['src_lon']})")
        print(f"  Vessels <= 5 km:    {diag_row['vessels_5km']}")
        print(f"  Vessels <= 10 km:   {diag_row['vessels_10km']}")
        print(f"  Vessels <= 25 km:   {diag_row['vessels_25km']}")
        print(f"  Closest Vessel:     {diag_row['closest_vessel_id']} at {diag_row['closest_dist_km']} km")
        print(f"  Closest Timestamp:  {diag_row['closest_timestamp']}")
    else:
        print("  Spill spill_497182 not found in detection_diagnostic_report.csv")
        return

    # 2. Run live hindcast to compare source coordinates
    weather_dir = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
    ocean_dir = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"
    if not ocean_dir.exists():
        ocean_dir = PROJECT_ROOT / "data" / "copernicus" / "raw" / "yearly"

    weather_svc = WeatherService(weather_yearly_dir=weather_dir, ocean_yearly_dir=ocean_dir)
    engine = AttributionEngine(weather_service=weather_svc)

    obs_time = datetime.fromisoformat("2019-01-19T03:42:58+00:00")
    obs_lat, obs_lon = 35.0827, 24.0254
    age_hours = 16.8

    source = engine.hindcast_service.backward_ensemble(
        obs_latitude=obs_lat,
        obs_longitude=obs_lon,
        obs_time=obs_time,
        duration_hours=age_hours,
    )

    print("\n=== 2. HINDCAST COMPARISON ===")
    print(f"  Live Hindcast Centroid: ({source.centroid_latitude:.4f}, {source.centroid_longitude:.4f}), radius={source.radius_km:.2f} km")
    print(f"  CSV Diagnostic Source:  ({float(diag_row['src_lat']):.4f}, {float(diag_row['src_lon']):.4f}), radius={float(diag_row['source_radius_km']):.2f} km")

    # 3. Query PostgreSQL for SYNTH-Y2019-000169 around estimated release time
    vessel_id = diag_row.get("closest_vessel_id") or "SYNTH-Y2019-000169"
    rel_time = obs_time - timedelta(hours=age_hours)
    w_start = rel_time - timedelta(hours=2)
    w_end = rel_time + timedelta(hours=2)

    print(f"\n=== 3. VESSEL {vessel_id} POSITIONS IN POSTGRESQL ===")
    print(f"  Time Window: {w_start.isoformat()} to {w_end.isoformat()}")

    async with SessionLocal() as db:
        query = text("""
            SELECT 
                vessel_id, timestamp, latitude, longitude, speed, scenario_id,
                ROUND((ST_Distance(geometry::geography, ST_SetSRID(ST_Point(:src_lon, :src_lat), 4326)::geography)/1000.0)::numeric, 2) AS dist_from_csv_src_km,
                ROUND((ST_Distance(geometry::geography, ST_SetSRID(ST_Point(:live_lon, :live_lat), 4326)::geography)/1000.0)::numeric, 2) AS dist_from_live_src_km
            FROM ais_positions
            WHERE vessel_id = :vessel_id
              AND timestamp BETWEEN :w_start AND :w_end
            ORDER BY timestamp;
        """)
        res = await db.execute(query, {
            "vessel_id": vessel_id,
            "w_start": w_start,
            "w_end": w_end,
            "src_lat": float(diag_row["src_lat"]),
            "src_lon": float(diag_row["src_lon"]),
            "live_lat": source.centroid_latitude,
            "live_lon": source.centroid_longitude,
        })
        rows = res.fetchall()
        print(f"  Found {len(rows)} AIS pings:")
        for r in rows:
            print(f"    {r.timestamp} | lat={r.latitude:.4f}, lon={r.longitude:.4f} | dist_to_csv_src={r.dist_from_csv_src_km} km | dist_to_live_src={r.dist_from_live_src_km} km | scenario={r.scenario_id}")

        # 4. Test candidate retrieval at incremental radii
        print("\n=== 4. LIVE CANDIDATE RETRIEVAL AT INCREASING RADII ===")
        for r_km in [5.0, 10.0, 15.0, 20.0, 25.0, 30.0]:
            cands = await engine.ais_repository.get_candidate_vessels(
                db=db,
                latitude=source.centroid_latitude,
                longitude=source.centroid_longitude,
                radius_km=r_km,
                start_time=w_start,
                end_time=w_end,
            )
            print(f"  Radius {r_km:4.1f} km -> Candidates found: {len(cands)} {cands}")


if __name__ == "__main__":
    asyncio.run(debug())