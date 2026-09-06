import asyncio
from datetime import datetime, timezone
from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.services.attribution_engine import AttributionEngine
from app.services.spill_catalog_service import SpillCatalogService
from app.services.weather_service import WeatherService

if hasattr(database, "AsyncSessionLocal"):
    SessionLocal = database.AsyncSessionLocal
elif hasattr(database, "async_session"):
    SessionLocal = database.async_session
elif hasattr(database, "engine"):
    SessionLocal = async_sessionmaker(
        database.engine, class_=AsyncSession, expire_on_commit=False
    )
else:
    raise RuntimeError("Could not resolve database sessionmaker.")


def get_weather_service_instance() -> WeatherService:
    """Builds WeatherService matching the app router configuration."""
    weather_dir = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
    ocean_dir = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"

    # Fallback to copernicus folder if ocean raw yearly is organized under copernicus
    if not ocean_dir.exists():
        alt_ocean = PROJECT_ROOT / "data" / "copernicus" / "raw" / "yearly"
        if alt_ocean.exists():
            ocean_dir = alt_ocean

    return WeatherService(
        weather_yearly_dir=weather_dir,
        ocean_yearly_dir=ocean_dir,
    )


async def test():
    # 1. Initialize catalog
    print("Initializing SpillCatalogService...")
    SpillCatalogService.initialize()

    total_count = SpillCatalogService.get_total_count()
    all_spills = SpillCatalogService.get_all_spills(limit=total_count)
    spills_with_candidates = [
        s for s in all_spills if int(s.get("candidate_count") or 0) > 0
    ]

    print("\n=== SPILL CATALOG VERIFICATION ===")
    print(f"Total Spills in Catalog:         {total_count}")
    print(f"Spills with candidate_count > 0:   {len(spills_with_candidates)}")

    # 2. Pick a newly activated spill beyond the initial 97 (e.g., index 150)
    test_idx = 150 if len(spills_with_candidates) > 150 else len(spills_with_candidates) - 1
    test_spill = spills_with_candidates[test_idx]

    spill_id = test_spill["spill_id"]
    lat = float(test_spill["observation_latitude"])
    lon = float(test_spill["observation_longitude"])
    age_hours = float(test_spill.get("estimated_age_hours", 12.0))

    raw_time = test_spill["detected_at"]
    if isinstance(raw_time, str):
        obs_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    else:
        obs_time = raw_time

    if obs_time.tzinfo is None:
        obs_time = obs_time.replace(tzinfo=timezone.utc)

    print(f"\n=== LIVE BACKTRACK & ATTRIBUTION TEST ===")
    print(f"Testing Spill ID:     {spill_id} (Index #{test_idx})")
    print(f"Observation Point:    ({lat:.4f}, {lon:.4f})")
    print(f"Detection Time:       {obs_time.isoformat()}")
    print(f"Drift Duration:       {age_hours} hours")
    print(f"Catalog Candidate:    {test_spill.get('ranked_top_vessel')} ({test_spill.get('candidate_count')} total)")

    # 3. Execute live AttributionEngine run
    weather_svc = get_weather_service_instance()
    engine = AttributionEngine(weather_service=weather_svc)

    async with SessionLocal() as db:
        res = await engine.attribute(
            db=db,
            observation_latitude=lat,
            observation_longitude=lon,
            observation_time=obs_time,
            drift_duration_hours=age_hours,
        )

    cand_count = res.get("candidate_count", 0)
    print(f"\nLive Candidates Found in PostgreSQL: {cand_count}")

    candidates = res.get("candidates", [])
    if candidates:
        top_cand = candidates[0]
        print(f"Top Attributed Vessel: {top_cand.get('vessel_id')}")
        print(f"Total Score:           {top_cand.get('score', 0.0):.3f}")
        print(f"Proximity Score:       {top_cand.get('proximity_score', 0.0):.3f}")
        print(f"Temporal Score:        {top_cand.get('temporal_score', 0.0):.3f}")
        print(f"Closest Distance:      {top_cand.get('closest_distance_km', 0.0):.2f} km")


if __name__ == "__main__":
    asyncio.run(test())