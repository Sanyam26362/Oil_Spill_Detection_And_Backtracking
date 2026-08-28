from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.drift_engine import DriftEngine
from app.services.weather_service import WeatherService

from scripts.synthetic.generate_synthetic_ais import (
    generate_scenario_dataset,
)
from scripts.synthetic.scenario import (
    SyntheticScenarioConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ERA5_PATH = (
    PROJECT_ROOT
    / "data/weather/raw/era5_wind_2019-07-event.nc"
)

CMEMS_PATH = (
    PROJECT_ROOT
    / "data/ocean/raw/med_currents_2019-07-event.nc"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/ais/processed"
)


def main() -> None:

    release_time = datetime(
        2019,
        7,
        15,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    true_lat = 33.5
    true_lon = 34.0

    drift_duration_hours = 6.0

    # --------------------------------------------------------------
    # Generate the synthetic SAR observation from real historical
    # ERA5 + CMEMS forcing.
    # --------------------------------------------------------------

    with WeatherService(
        era5_path=ERA5_PATH,
        cmems_path=CMEMS_PATH,
    ) as weather:

        drift_engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        trajectory = drift_engine.forward_drift(
            start_latitude=true_lat,
            start_longitude=true_lon,
            start_time=release_time,
            duration_hours=drift_duration_hours,
            timestep_minutes=15,
        )

        observation = trajectory.end

    config = SyntheticScenarioConfig(
        scenario_id="scenario-002",

        release_lat=true_lat,
        release_lon=true_lon,
        release_time=release_time,

        observation_lat=observation.latitude,
        observation_lon=observation.longitude,
        observation_time=observation.timestamp,

        drift_duration_hours=drift_duration_hours,

        bounds_lat_min=33.0,
        bounds_lat_max=34.5,

        bounds_lon_min=33.5,
        bounds_lon_max=35.0,

        num_background_vessels=150,
        num_decoy_vessels=4,

        source_vessel_id="SYNTH-000011",

        decoy_start_id=12,

        windage=0.03,

        seed=42,
    )

    df, ground_truth = (
        generate_scenario_dataset(config)
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    ais_path = (
        OUTPUT_DIR
        / "synthetic_scenario_002.csv"
    )

    ground_truth_path = (
        OUTPUT_DIR
        / "synthetic_scenario_002_ground_truth.json"
    )

    observation_path = (
        OUTPUT_DIR
        / "synthetic_scenario_002_observation.json"
    )

    # AIS.
    df.to_csv(
        ais_path,
        index=False,
    )

    # Ground truth — evaluation only.
    with ground_truth_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            ground_truth,
            f,
            indent=2,
        )

    # Observation — this is what attribution is allowed to see.
    observation_payload = {
        "scenario_id": config.scenario_id,
        "synthetic": True,
        "observation": {
            "latitude": observation.latitude,
            "longitude": observation.longitude,
            "timestamp": observation.timestamp.isoformat().replace(
                "+00:00",
                "Z",
            ),
        },
    }

    with observation_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            observation_payload,
            f,
            indent=2,
        )

    print()
    print("=" * 80)
    print("SCENARIO 002 GENERATED")
    print("=" * 80)

    print(
        f"Source vessel       : "
        f"{config.source_vessel_id}"
    )

    print(
        f"Release             : "
        f"{config.release_lat:.6f}, "
        f"{config.release_lon:.6f}"
    )

    print(
        f"Release time        : "
        f"{config.release_time}"
    )

    print()

    print("SYNTHETIC SAR OBSERVATION")
    print(
        f"Location            : "
        f"{observation.latitude:.6f}, "
        f"{observation.longitude:.6f}"
    )

    print(
        f"Time                : "
        f"{observation.timestamp}"
    )

    print()

    print(
        f"AIS records         : "
        f"{len(df):,}"
    )

    print(
        f"AIS                 : "
        f"{ais_path}"
    )

    print(
        f"Observation         : "
        f"{observation_path}"
    )

    print(
        f"Ground truth        : "
        f"{ground_truth_path}"
    )


if __name__ == "__main__":
    main()