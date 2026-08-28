from datetime import timedelta
from pathlib import Path

from scripts.synthetic.scenario import SpillScenario
from scripts.synthetic.generate_synthetic_ais import (
    generate_dataset,
    write_csv,
    write_ground_truth,
)

from app.services.drift_engine import DriftEngine
from app.services.weather_service import WeatherService


ERA5_FILE = (
    "data/weather/raw/"
    "era5_wind_2019-07-event.nc"
)

CMEMS_FILE = (
    "data/ocean/raw/"
    "med_currents_2019-07-event.nc"
)


def build_scenario() -> SpillScenario:
    from datetime import datetime, timezone

    return SpillScenario(
        scenario_id="scenario-002",

        origin_lat=33.50,
        origin_lon=34.00,

        origin_time=datetime(
            2019,
            7,
            15,
            12,
            0,
            0,
            tzinfo=timezone.utc,
        ),

        observation_delay_hours=6.0,

        windage=0.03,

        region_min_lat=30.0,
        region_max_lat=37.0,

        region_min_lon=30.0,
        region_max_lon=36.0,

        duration_hours=6,

        background_vessels=150,
        candidate_vessels=5,

        suspicious_vessel_index=0,

        random_seed=42,
    )


def main() -> None:

    scenario = build_scenario()

    # --------------------------------------------------------------
    # 1. Generate AIS.
    # --------------------------------------------------------------

    records = generate_dataset(scenario)

    ais_output = Path(
        "data/ais/processed/"
        "synthetic_scenario_002.csv"
    )

    ground_truth_output = Path(
        "data/ais/processed/"
        "synthetic_scenario_002_ground_truth.json"
    )

    write_csv(
        records,
        ais_output,
    )

    # --------------------------------------------------------------
    # 2. Generate oil observation using REAL environmental data.
    # --------------------------------------------------------------

    observation_time = (
        scenario.origin_time
        + timedelta(
            hours=scenario.observation_delay_hours
        )
    )

    with WeatherService(
        era5_path=ERA5_FILE,
        cmems_path=CMEMS_FILE,
    ) as weather:

        drift_engine = DriftEngine(
            weather_service=weather,
            windage=scenario.windage,
        )

        forward = drift_engine.forward_drift(
            start_latitude=scenario.origin_lat,
            start_longitude=scenario.origin_lon,
            start_time=scenario.origin_time,
            duration_hours=scenario.observation_delay_hours,
            timestep_minutes=15,
        )

    observation = forward.end

    # --------------------------------------------------------------
    # 3. Write the evaluation ground truth.
    # --------------------------------------------------------------

    import json

    suspicious_number = (
        scenario.background_vessels
        + 1
        + scenario.suspicious_vessel_index
    )

    ground_truth = {
        "scenario_id": scenario.scenario_id,

        "synthetic": True,

        "source": {
            "latitude": scenario.origin_lat,
            "longitude": scenario.origin_lon,
            "timestamp": (
                scenario.origin_time.isoformat()
            ),
        },

        "observation": {
            "latitude": observation.latitude,
            "longitude": observation.longitude,
            "timestamp": observation.timestamp.isoformat(),
        },

        "oil_model": {
            "windage": scenario.windage,
            "observation_delay_hours": (
                scenario.observation_delay_hours
            ),
        },

        "ground_truth_suspicious_vessel": (
            f"SYNTH-{suspicious_number:06d}"
        ),

        "candidate_vessels": [
            (
                f"SYNTH-"
                f"{scenario.background_vessels + i + 1:06d}"
            )
            for i in range(
                scenario.candidate_vessels
            )
        ],
    }

    ground_truth_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ground_truth_output.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            ground_truth,
            f,
            indent=2,
        )

    # --------------------------------------------------------------
    # 4. Console summary.
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print("END-TO-END SYNTHETIC SCENARIO")
    print("=" * 80)

    print(
        f"Scenario             : "
        f"{scenario.scenario_id}"
    )

    print(
        f"Source vessel        : "
        f"SYNTH-{suspicious_number:06d}"
    )

    print()

    print("TRUE OIL SOURCE")
    print(
        f"Latitude             : "
        f"{scenario.origin_lat:.6f}"
    )

    print(
        f"Longitude            : "
        f"{scenario.origin_lon:.6f}"
    )

    print(
        f"Release time         : "
        f"{scenario.origin_time}"
    )

    print()

    print("SYNTHETIC SAR OBSERVATION")
    print(
        f"Latitude             : "
        f"{observation.latitude:.6f}"
    )

    print(
        f"Longitude            : "
        f"{observation.longitude:.6f}"
    )

    print(
        f"Observation time     : "
        f"{observation.timestamp}"
    )

    print()

    print("AIS")
    print(
        f"Records              : "
        f"{len(records):,}"
    )

    print(
        f"AIS output            : "
        f"{ais_output}"
    )

    print(
        f"Ground truth          : "
        f"{ground_truth_output}"
    )


if __name__ == "__main__":
    main()