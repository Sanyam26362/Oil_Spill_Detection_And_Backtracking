from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.scoring_engine import ScoringEngine
from app.services.weather_service import WeatherService


PROJECT_ROOT = Path(__file__).resolve().parents[2]

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


def load_observation() -> dict:
    """
    Load ONLY the synthetic SAR observation.

    Ground truth is intentionally not loaded.
    """

    path = (
        DATA_DIR
        / "synthetic_scenario_002_observation.json"
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        payload = json.load(f)

    return payload["observation"]


def load_ais_fixture() -> pd.DataFrame:

    path = (
        DATA_DIR
        / "synthetic_scenario_002.csv"
    )

    df = pd.read_csv(path)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    return df


def main() -> None:

    observation = load_observation()

    obs_time = pd.Timestamp(
        observation["timestamp"]
    )

    df = load_ais_fixture()

    with WeatherService(
        era5_path=ERA5_PATH,
        cmems_path=CMEMS_PATH,
    ) as weather:

        drift_engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        hindcast_service = (
            HindcastService(
                drift_engine=drift_engine
            )
        )

        estimate = (
            hindcast_service.backward_ensemble(
                obs_latitude=observation["latitude"],
                obs_longitude=observation["longitude"],
                obs_time=obs_time.to_pydatetime(),
                duration_hours=6,
                ensemble_size=100,
                initial_radius_m=500,
                timestep_minutes=15,
                random_seed=42,
            )
        )

    # ==============================================================
    # Candidate extraction for offline synthetic fixture.
    #
    # Production candidate extraction should use AISRepository +
    # PostGIS instead.
    # ==============================================================

    estimated_release_time = (
        obs_time
        - timedelta(hours=6)
    )

    search_radius_km = max(
        estimate.radius_km + 5.0,
        5.0,
    )

    time_start = (
        estimated_release_time
        - timedelta(hours=2)
    )

    time_end = (
        estimated_release_time
        + timedelta(hours=2)
    )

    candidate_ids = []

    for vessel_id, vessel_df in df.groupby(
        "vessel_id"
    ):

        vessel_df = vessel_df[
            (
                vessel_df["timestamp"]
                >= time_start
            )
            &
            (
                vessel_df["timestamp"]
                <= time_end
            )
        ].copy()

        if vessel_df.empty:
            continue

        for _, row in vessel_df.iterrows():

            distance = (
                HindcastService.haversine_km(
                    estimate.centroid_latitude,
                    estimate.centroid_longitude,
                    row["latitude"],
                    row["longitude"],
                )
            )

            if distance <= search_radius_km:
                candidate_ids.append(
                    vessel_id
                )
                break

    candidate_ids = sorted(
        set(candidate_ids)
    )

    # ==============================================================
    # Score
    # ==============================================================

    scorer = ScoringEngine()

    results = []

    for vessel_id in candidate_ids:

        score = scorer.score_vessel(
            vessel_id=vessel_id,
            df=df,
            source_latitude=(
                estimate.centroid_latitude
            ),
            source_longitude=(
                estimate.centroid_longitude
            ),
            estimated_release_time=(
                estimated_release_time
            ),
        )

        results.append(
            score.__dict__
        )

    results_df = (
        pd.DataFrame(results)
        .sort_values(
            "total_score",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    print()
    print("=" * 100)
    print("BLIND ATTRIBUTION RESULT")
    print("=" * 100)

    print(
        f"Estimated source : "
        f"{estimate.centroid_latitude:.6f}, "
        f"{estimate.centroid_longitude:.6f}"
    )

    print(
        f"Source radius    : "
        f"{estimate.radius_km:.3f} km"
    )

    print(
        f"Candidates       : "
        f"{len(candidate_ids)}"
    )

    print()

    if results_df.empty:
        print("No candidates found.")
        return

    print(
        results_df.to_string(
            index=False
        )
    )

    print()

    print(
        f"TOP PREDICTION: "
        f"{results_df.iloc[0]['vessel_id']}"
    )


if __name__ == "__main__":
    main()