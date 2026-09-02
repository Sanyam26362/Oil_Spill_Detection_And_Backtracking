import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from scripts.synthetic.generate_synthetic_ais import (
    generate_scenario_dataset,
)
from scripts.synthetic.scenario import (
    SyntheticScenarioConfig,
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/ais/processed"
)

def main() -> None:
    # 1. GEOGRAPHY: latitude ≈ 35.05, longitude ≈ 24.04
    true_lat = 35.05
    true_lon = 24.04

    release_time = datetime(
        2019,
        7,
        15,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    # 2. AIS-ONLY SCOPE: Mock the observation
    observation_lat = 35.03
    observation_lon = 24.06
    observation_time = datetime(
        2019,
        7,
        15,
        18,
        0,
        0,
        tzinfo=timezone.utc,
    )
    drift_duration_hours = 6.0

    # Configure Scenario 003
    config = SyntheticScenarioConfig(
        scenario_id="scenario-003",
        release_lat=true_lat,
        release_lon=true_lon,
        release_time=release_time,

        observation_lat=observation_lat,
        observation_lon=observation_lon,
        observation_time=observation_time,

        drift_duration_hours=drift_duration_hours,

        bounds_lat_min=34.5,
        bounds_lat_max=35.5,

        bounds_lon_min=23.5,
        bounds_lon_max=24.5,

        num_background_vessels=150,
        num_decoy_vessels=5,

        vessel_id_prefix="SYNTH-003-",
        source_vessel_id="SYNTH-003-SRC",
        decoy_start_id=1,

        decoy_behaviors=[
            "DCY01",
            "DCY02",
            "DCY03",
            "DCY04",
            "DCY05"
        ],

        windage=0.03,
        seed=42,
    )

    print("Generating scenario-003 dataset...")
    df, ground_truth = generate_scenario_dataset(config)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    ais_path = OUTPUT_DIR / "synthetic_scenario_003.csv"
    ground_truth_path = OUTPUT_DIR / "synthetic_scenario_003_ground_truth.json"

    # AIS
    df.to_csv(ais_path, index=False)

    # Ground truth
    with ground_truth_path.open("w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    print()
    print("=" * 80)
    print("SCENARIO 003 GENERATED")
    print("=" * 80)
    print(f"Source vessel       : {config.source_vessel_id}")
    print(f"Release             : {config.release_lat:.6f}, {config.release_lon:.6f}")
    print(f"Release time        : {config.release_time}")
    print()
    print(f"AIS records         : {len(df):,}")
    print(f"AIS                 : {ais_path}")
    print(f"Ground truth        : {ground_truth_path}")

if __name__ == "__main__":
    main()
