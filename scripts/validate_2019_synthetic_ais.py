import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.models.ais import AISPosition
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService
from scripts.test_scenario_004_e2e import haversine_km

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCENARIOS = [
    {"id": "scenario-001", "name": "001 (Clean Baseline)"},
    {"id": "scenario-002", "name": "002 (Different Env)"},
    {"id": "scenario-003", "name": "003 (Scoring Behaviors)"},
    {"id": "scenario-004", "name": "004 (E2E Baseline)"},
    {"id": "scenario-005", "name": "005 (Stress/Ambiguous)"},
]

OUTPUT_DIR = PROJECT_ROOT / "data" / "ais" / "processed"
WEATHER_DIR = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
OCEAN_DIR = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"

async def run_scenario(scenario_id: str, weather_service: WeatherService):
    """Run E2E attribution test for a single scenario against the FULL 2019 SYNTHETIC DATABASE."""
    gt_path = OUTPUT_DIR / f"synthetic_{scenario_id.replace('-', '_')}_ground_truth.json"

    if not gt_path.exists():
        logger.error(f"Ground truth not found for {scenario_id}: {gt_path}")
        return None

    with gt_path.open() as f:
        gt = json.load(f)

    if scenario_id == "scenario-002":
        obs_path = OUTPUT_DIR / f"synthetic_{scenario_id.replace('-', '_')}_observation.json"
        with obs_path.open() as f:
            obs_data = json.load(f)
        obs_lat = obs_data["observation"]["latitude"]
        obs_lon = obs_data["observation"]["longitude"]
        obs_time = datetime.fromisoformat(obs_data["observation"]["timestamp"].replace("Z", "+00:00"))

        drift_dur = 6.0
        true_lat = gt["source"]["latitude"]
        true_lon = gt["source"]["longitude"]
        true_vessel = gt["source"]["vessel_id"]
    elif scenario_id == "scenario-003":
        obs_lat = gt["observation"]["latitude"]
        obs_lon = gt["observation"]["longitude"]
        obs_time = datetime.fromisoformat(gt["observation"]["timestamp"].replace("Z", "+00:00"))
        drift_dur = gt["observation"]["drift_duration_hours"]
        true_lat = gt["source"]["latitude"]
        true_lon = gt["source"]["longitude"]
        true_vessel = gt["source"]["vessel_id"]
    else:
        fdv = gt.get("forward_drift_validation", {})
        obs_lat = fdv.get("generated_observation_lat")
        obs_lon = fdv.get("generated_observation_lon")
        obs_time = datetime.fromisoformat(fdv.get("generated_observation_time").replace("Z", "+00:00"))
        drift_dur = fdv.get("duration_hours", 6.0)
        true_lat = fdv.get("true_release_lat")
        true_lon = fdv.get("true_release_lon")
        true_vessel = gt["source"]["vessel_id"]

    engine = AttributionEngine(weather_service=weather_service)

    start_t = time.time()

    # CRITICAL: We pass scenario_id=None so it queries the full database!
    async with AsyncSessionLocal() as db:
        result = await engine.attribute(
            db=db,
            observation_latitude=obs_lat,
            observation_longitude=obs_lon,
            observation_time=obs_time,
            drift_duration_hours=drift_dur,
            synthetic_only=True,
            scenario_id=None, # <- THIS ENABLES THE FULL DB SEARCH!
        )

    runtime = time.time() - start_t

    candidates = result.get("candidates", [])
    est_src = result.get("source_estimate", {})

    if not est_src or "latitude" not in est_src:
        return {
            "scenario": scenario_id,
            "true_vessel": true_vessel,
            "error_km": 999.9,
            "candidates": len(candidates),
            "rank": "N/A",
            "runtime": runtime,
            "pass": False,
            "reason": "Hindcast failed"
        }

    error_km = haversine_km(true_lat, true_lon, est_src["latitude"], est_src["longitude"])

    rank = None
    for i, c in enumerate(candidates, 1):
        if c.get("vessel_id") == true_vessel:
            rank = i
            break

    passed = rank == 1 and error_km <= 5.0

    return {
        "scenario": scenario_id,
        "true_vessel": true_vessel,
        "error_km": error_km,
        "candidates": len(candidates),
        "rank": rank if rank else "N/A",
        "runtime": runtime,
        "pass": passed,
        "reason": "Success" if passed else "Wrong Rank or High Error"
    }

async def validate_database_metrics():
    logger.info("Validating database metrics...")
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT COUNT(*) FROM ais_positions"))
        total_rows = res.scalar_one()

        res = await db.execute(text("SELECT COUNT(DISTINCT vessel_id) FROM vessels"))
        total_vessels = res.scalar_one()

    return total_rows, total_vessels

async def main():
    print("=" * 80)
    print("2019 SYNTHETIC AIS VALIDATION")
    print("=" * 80)

    # 1. Database validation
    total_rows, total_vessels = await validate_database_metrics()
    print("\nDataset:")
    print(f"    Records: {total_rows:,}")
    print(f"    Vessels: {total_vessels:,}")
    print(f"    Coverage: 2019-01-01 -> 2019-12-31")

    # 2. Scenarios
    print("\nScenario Results:")
    print(f"{'Scenario':<12} {'True Source':<15} {'Error km':<10} {'Candidates':<12} {'Rank':<6} {'Runtime':<8} {'Result'}")
    print("-" * 75)

    ws = WeatherService(weather_yearly_dir=WEATHER_DIR, ocean_yearly_dir=OCEAN_DIR)

    all_passed = True
    results_list = []

    try:
        for s in SCENARIOS:
            res = await run_scenario(s["id"], ws)
            if res:
                results_list.append(res)
                rank_str = f"#{res['rank']}" if res['rank'] != 'N/A' else 'N/A'
                pass_str = "PASS" if res['pass'] else "FAIL"
                print(f"{s['id']:<12} {res['true_vessel']:<15} {res['error_km']:<10.2f} {res['candidates']:<12} {rank_str:<6} {res['runtime']:<8.2f} {pass_str}")
                if not res['pass']:
                    all_passed = False
            else:
                all_passed = False
    finally:
        ws.close()

    print("\n" + "=" * 80)
    if all_passed:
        print("Overall: PASS")
    else:
        print("Overall: FAIL")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
