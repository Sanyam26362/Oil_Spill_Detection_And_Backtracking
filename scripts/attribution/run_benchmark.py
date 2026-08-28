import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
import math
from pathlib import Path
import random

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine

from scripts.synthetic.scenario import SyntheticScenarioConfig
from scripts.synthetic.generate_synthetic_ais import generate_scenario_dataset
from scripts.synthetic.ingest_synthetic import ingest_scenario

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data/ais/processed"
ERA5_PATH = PROJECT_ROOT / "data/weather/raw/era5_wind_2019-07-event.nc"
CMEMS_PATH = PROJECT_ROOT / "data/ocean/raw/med_currents_2019-07-event.nc"

def generate_config(scenario_id: str, seed: int, hard: bool) -> SyntheticScenarioConfig:
    rng = np.random.default_rng(seed)
    
    # Randomize source location within ERA5/CMEMS bounds
    # ERA5 bounds approximately: lat 30-36, lon 24-30 ? 
    # Actually CMEMS 2019-07-event.nc is Med Sea. The verified event is 33.5, 34.0.
    release_lat = 33.5 + rng.uniform(-0.5, 0.5)
    release_lon = 34.0 + rng.uniform(-0.5, 0.5)
    
    # Release time somewhere around 2019-07-15 12:00 UTC
    release_time = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    release_time += pd.Timedelta(hours=rng.uniform(-24, 24))
    
    return SyntheticScenarioConfig(
        scenario_id=scenario_id,
        release_lat=release_lat,
        release_lon=release_lon,
        release_time=release_time,
        observation_lat=0.0, # Will be filled by DriftEngine
        observation_lon=0.0,
        observation_time=release_time + pd.Timedelta(hours=6),
        drift_duration_hours=6.0,
        bounds_lat_min=release_lat - 1.5,
        bounds_lat_max=release_lat + 1.5,
        bounds_lon_min=release_lon - 1.5,
        bounds_lon_max=release_lon + 1.5,
        num_background_vessels=150,
        num_decoy_vessels=6 if hard else 2,
        seed=seed
    )

async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    scenarios = []
    # 20 base, 20 hard
    for i in range(1, 41):
        hard = i > 20
        scenario_id = f"BENCHMARK-{i:03d}"
        seed = 42 + i
        config = generate_config(scenario_id, seed, hard)
        scenarios.append(config)

    with WeatherService(era5_path=ERA5_PATH, cmems_path=CMEMS_PATH) as weather:
        drift_engine = DriftEngine(weather_service=weather, windage=0.03)
        attribution_engine = AttributionEngine(weather_service=weather)

        results = []

        for config in scenarios:
            logger.info(f"--- Running {config.scenario_id} ---")
            
            # 1. Generate Oil Observation
            traj = drift_engine.forward_drift(
                start_latitude=config.release_lat,
                start_longitude=config.release_lon,
                start_time=config.release_time,
                duration_hours=config.drift_duration_hours,
            )
            
            if not traj.states:
                logger.error(f"Failed to generate forward drift for {config.scenario_id}")
                continue
                
            config.observation_lat = traj.end.latitude
            config.observation_lon = traj.end.longitude
            config.observation_time = traj.end.timestamp
            
            # 2. Generate Synthetic AIS
            df, ground_truth = generate_scenario_dataset(config)
            
            csv_path = DATA_DIR / f"{config.scenario_id}.csv"
            gt_path = DATA_DIR / f"{config.scenario_id}_gt.json"
            
            df.to_csv(csv_path, index=False)
            with open(gt_path, "w") as f:
                json.dump(ground_truth, f)
            
            # 3. Ingest into PostGIS
            await ingest_scenario(str(csv_path), str(gt_path))
            
            # 4. Blind Attribution
            async with AsyncSessionLocal() as db:
                pred = await attribution_engine.attribute(
                    db=db,
                    observation_latitude=config.observation_lat,
                    observation_longitude=config.observation_lon,
                    observation_time=config.observation_time,
                    drift_duration_hours=config.drift_duration_hours,
                    synthetic_only=True,
                    scenario_id=config.scenario_id
                )
            
            # 5. Evaluate
            true_vessel = ground_truth["source"]["vessel_id"]
            candidates = pred["candidates"]
            
            ranked_vessels = [c["vessel_id"] for c in candidates]
            
            if true_vessel in ranked_vessels:
                rank = ranked_vessels.index(true_vessel) + 1
                mrr = 1.0 / rank
                top1 = rank == 1
                top3 = rank <= 3
                recall = True
            else:
                rank = -1
                mrr = 0.0
                top1 = False
                top3 = False
                recall = False
                
            source_est = pred["source_estimate"]
            source_error = HindcastService.haversine_km(
                source_est["latitude"], source_est["longitude"],
                config.release_lat, config.release_lon
            ) if source_est else 999.0
            
            res = {
                "scenario_id": config.scenario_id,
                "hard": config.num_decoy_vessels > 2,
                "true_vessel": true_vessel,
                "rank": rank,
                "mrr": mrr,
                "top1": top1,
                "top3": top3,
                "recall": recall,
                "source_error_km": source_error,
                "candidate_count": pred["candidate_count"],
            }
            results.append(res)
            logger.info(f"Result: {res}")
            
        # Summary
        res_df = pd.DataFrame(results)
        res_df.to_csv(DATA_DIR / "benchmark_results.csv", index=False)
        
        summary = {
            "total_scenarios": 40,
            "successful_runs": len(res_df),
            "top1_accuracy": res_df["top1"].mean(),
            "top3_accuracy": res_df["top3"].mean(),
            "candidate_recall": res_df["recall"].mean(),
            "mrr": res_df["mrr"].mean(),
            "mean_source_error": res_df["source_error_km"].mean(),
            "median_source_error": res_df["source_error_km"].median(),
            "mean_candidates": res_df["candidate_count"].mean(),
            "median_candidates": res_df["candidate_count"].median(),
            "min_candidates": res_df["candidate_count"].min(),
            "max_candidates": res_df["candidate_count"].max(),
        }
        
        with open(DATA_DIR / "benchmark_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
            
        logger.info(f"Benchmark Summary: {summary}")

class HindcastService:
    @staticmethod
    def haversine_km(lat1, lon1, lat2, lon2):
        radius_km = 6371.0088
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2
        return 2.0 * radius_km * math.asin(math.sqrt(a))

if __name__ == "__main__":
    asyncio.run(main())
