import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone

project_root = str(Path(__file__).resolve().parents[1])
sys.path.append(project_root)

from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from scripts.synthetic.scenario import SyntheticScenarioConfig
from scripts.synthetic.generate_synthetic_ais import generate_scenario_dataset
from scripts.attribution.score_candidates import get_candidates_in_region, score_vessel

def main():
    era5_path = os.path.join(project_root, "data", "weather", "raw", "era5_wind_2019-07-event.nc")
    cmems_path = os.path.join(project_root, "data", "ocean", "raw", "med_currents_2019-07-event.nc")
    
    release_time = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    drift_duration = 6.0
    num_tests = 10
    
    # We use 50 background vessels per scenario to keep the test fast (10 iterations * 50 = 500 unique background tracks)
    bg_vessels_per_test = 50 
    
    rng = np.random.default_rng(999)
    results_summary = []

    print(f"Starting Bulk Test: {num_tests} Random Spills...\n")

    with WeatherService(era5_path=era5_path, cmems_path=cmems_path) as weather:
        drift_engine = DriftEngine(weather_service=weather, windage=0.03)
        hindcast_service = HindcastService(drift_engine=drift_engine)
        
        for i in range(num_tests):
            test_id = i + 1
            print(f"--- Generating Scenario {test_id}/{num_tests} ---")
            
            # 1. Pick a random coordinate safely within the ERA5/CMEMS NetCDF bounds
            true_lat = round(rng.uniform(33.2, 33.8), 4)
            true_lon = round(rng.uniform(33.7, 34.3), 4)
            
            # 2. Forward Drift (Simulate the SAR satellite detection)
            forward_traj = drift_engine.forward_drift(
                start_latitude=true_lat,
                start_longitude=true_lon,
                start_time=release_time,
                duration_hours=drift_duration,
                timestep_minutes=15
            )
            observation = forward_traj.end
            
            # 3. Generate the Synthetic AIS Data (In-Memory)
            config = SyntheticScenarioConfig(
                scenario_id=f"bulk-scenario-{test_id:03d}",
                release_lat=true_lat,
                release_lon=true_lon,
                release_time=release_time,
                observation_lat=observation.latitude,
                observation_lon=observation.longitude,
                observation_time=observation.timestamp,
                drift_duration_hours=drift_duration,
                bounds_lat_min=33.0, bounds_lat_max=34.5,
                bounds_lon_min=33.5, bounds_lon_max=35.0,
                num_background_vessels=bg_vessels_per_test,
                seed=42 + i # Change seed so each scenario has completely different background ships
            )
            df, ground_truth = generate_scenario_dataset(config)
            
            # 4. FIX: Clean timestamps before pandas math
            df['timestamp'] = df['timestamp'].astype(str).str.replace('+00:00Z', '+00:00', regex=False)
            df['timestamp'] = df['timestamp'].str.replace('Z', '+00:00', regex=False)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_localize(None)
            
            # 5. Run the Blind Backward Hindcast
            estimate = hindcast_service.backward_ensemble(
                obs_latitude=observation.latitude,
                obs_longitude=observation.longitude,
                obs_time=observation.timestamp.replace(tzinfo=None),
                duration_hours=drift_duration,
                ensemble_size=30, # Fast ensemble for bulk testing
                timestep_minutes=15
            )
            
            # 6. Score Candidates
            candidates, _ = get_candidates_in_region(
                df, estimate.centroid_latitude, estimate.centroid_longitude, 
                estimate.radius_km, release_time.replace(tzinfo=None)
            )
            
            best_vessel = None
            best_score = -1.0
            
            for vessel in candidates:
                score, _, _ = score_vessel(vessel, df, estimate.centroid_latitude, estimate.centroid_longitude, release_time.replace(tzinfo=None))
                if score > best_score:
                    best_score = score
                    best_vessel = vessel
                    
            # 7. Check if we caught the right ship
            is_success = (best_vessel == ground_truth['ground_truth_suspicious_vessel'])
            
            results_summary.append({
                "Test": test_id,
                "Spill Lat": true_lat,
                "Spill Lon": true_lon,
                "Candidates": len(candidates),
                "Top Ranked Vessel": best_vessel,
                "Score": round(best_score, 4),
                "Success": "✅ PASS" if is_success else "❌ FAIL"
            })
            
    # Print Final Scorecard
    print("\n================= 10-SPILL BULK TEST RESULTS =================")
    summary_df = pd.DataFrame(results_summary)
    print(summary_df.to_string(index=False))
    print("==============================================================")
    
    success_rate = (summary_df['Success'] == '✅ PASS').mean() * 100
    print(f"\nFINAL ACCURACY: {success_rate:.0f}%")

if __name__ == "__main__":
    main()