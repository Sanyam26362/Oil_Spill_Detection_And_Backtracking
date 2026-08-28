from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.attribution.score_candidates import (
    load_observation,
    load_ais_fixture,
)

from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.scoring_engine import ScoringEngine
from app.services.weather_service import WeatherService


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = (
    PROJECT_ROOT
    / "data/ais/processed"
)

ERA5_PATH = (
    PROJECT_ROOT
    / "data/weather/raw/era5_wind_2019-07-event.nc"
)

CMEMS_PATH = (
    PROJECT_ROOT
    / "data/ocean/raw/med_currents_2019-07-event.nc"
)


def main() -> None:

    observation = load_observation()
    df = load_ais_fixture()

    truth_path = (
        DATA_DIR
        / "synthetic_scenario_002_ground_truth.json"
    )

    with truth_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        ground_truth = json.load(f)

    # --------------------------------------------------------------
    # Re-run exactly the same blind attribution path.
    # --------------------------------------------------------------

    with WeatherService(
        era5_path=ERA5_PATH,
        cmems_path=CMEMS_PATH,
    ) as weather:

        engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        hindcast = HindcastService(
            drift_engine=engine
        )

        estimate = (
            hindcast.backward_ensemble(
                obs_latitude=observation["latitude"],
                obs_longitude=observation["longitude"],
                obs_time=pd.Timestamp(
                    observation["timestamp"]
                ).to_pydatetime(),
                duration_hours=6,
                ensemble_size=100,
                initial_radius_m=500,
                timestep_minutes=15,
                random_seed=42,
            )
        )

    release_time = (
        pd.Timestamp(
            ground_truth["source"]["timestamp"]
        )
    )

    # Same candidate search as blind scorer.
    candidates = []

    search_radius = max(
        estimate.radius_km + 5,
        5,
    )

    for vessel_id, vessel_df in df.groupby(
        "vessel_id"
    ):

        vessel_df = vessel_df[
            (
                vessel_df["timestamp"]
                >= release_time
                - pd.Timedelta(hours=2)
            )
            &
            (
                vessel_df["timestamp"]
                <= release_time
                + pd.Timedelta(hours=2)
            )
        ]

        for _, row in vessel_df.iterrows():

            distance = (
                HindcastService.haversine_km(
                    estimate.centroid_latitude,
                    estimate.centroid_longitude,
                    row["latitude"],
                    row["longitude"],
                )
            )

            if distance <= search_radius:
                candidates.append(vessel_id)
                break

    scorer = ScoringEngine()

    results = []

    for vessel_id in sorted(set(candidates)):

        result = scorer.score_vessel(
            vessel_id=vessel_id,
            df=df,
            source_latitude=estimate.centroid_latitude,
            source_longitude=estimate.centroid_longitude,
            estimated_release_time=release_time,
        )

        results.append(result.__dict__)

    result_df = (
        pd.DataFrame(results)
        .sort_values(
            "total_score",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    predicted = (
        result_df.iloc[0]["vessel_id"]
        if not result_df.empty
        else None
    )

    truth = (
        ground_truth[
            "source"
        ]["vessel_id"]
    )

    print()
    print("=" * 80)
    print("POST-HOC EVALUATION")
    print("=" * 80)

    print(
        f"Predicted vessel : {predicted}"
    )

    print(
        f"Ground truth     : {truth}"
    )

    print()

    if predicted == truth:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")

    print()
    print(
        result_df[
            [
                "vessel_id",
                "total_score",
                "proximity_score",
                "temporal_score",
                "slowdown_score",
                "loiter_score",
                "approach_score",
                "departure_score",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()