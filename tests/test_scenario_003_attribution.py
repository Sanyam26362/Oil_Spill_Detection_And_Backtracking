from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

WEATHER_DIR = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
OCEAN_DIR = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"


# ---------------------------------------------------------------------------
# Scenario-003 ground truth
# ---------------------------------------------------------------------------

SCENARIO_ID = "scenario-003"

TRUE_SOURCE = "SYNTH-003-SRC"

OBSERVATION_LATITUDE = 35.03
OBSERVATION_LONGITUDE = 24.06

OBSERVATION_TIME = datetime(
    2019,
    7,
    15,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)

DRIFT_DURATION_HOURS = 6.0

EXPECTED_CANDIDATES = [
    "SYNTH-003-SRC",
    "SYNTH-003-DCY01",
    "SYNTH-003-DCY02",
    "SYNTH-003-DCY03",
    "SYNTH-003-DCY04",
    "SYNTH-003-DCY05",
]


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

async def main() -> None:

    print("=" * 90)
    print("SCENARIO-003 END-TO-END ATTRIBUTION TEST")
    print("=" * 90)

    print()
    print("SCENARIO")
    print("-" * 90)
    print(f"Scenario ID           : {SCENARIO_ID}")
    print(f"True source vessel    : {TRUE_SOURCE}")

    print()
    print("OBSERVATION")
    print("-" * 90)
    print(f"Latitude              : {OBSERVATION_LATITUDE}")
    print(f"Longitude             : {OBSERVATION_LONGITUDE}")
    print(f"Time                  : {OBSERVATION_TIME}")
    print(f"Drift duration        : {DRIFT_DURATION_HOURS} hours")

    print()
    print("EXPECTED CANDIDATES")
    print("-" * 90)

    for vessel_id in EXPECTED_CANDIDATES:
        print(vessel_id)

    # -----------------------------------------------------------------------
    # Weather / ocean service
    #
    # AttributionEngine requires WeatherService because the hindcast uses it.
    # We are NOT mocking it here. This is the real end-to-end test.
    # -----------------------------------------------------------------------

    weather = WeatherService(
        weather_yearly_dir=WEATHER_DIR,
        ocean_yearly_dir=OCEAN_DIR,
    )

    try:

        # -------------------------------------------------------------------
        # Create attribution engine
        # -------------------------------------------------------------------

        engine = AttributionEngine(
            weather_service=weather,
        )

        # -------------------------------------------------------------------
        # Run actual attribution pipeline
        # -------------------------------------------------------------------

        async with AsyncSessionLocal() as db:

            print()
            print("=" * 90)
            print("RUNNING ATTRIBUTION ENGINE")
            print("=" * 90)

            result = await engine.attribute(
                db=db,
                observation_latitude=OBSERVATION_LATITUDE,
                observation_longitude=OBSERVATION_LONGITUDE,
                observation_time=OBSERVATION_TIME,
                drift_duration_hours=DRIFT_DURATION_HOURS,

                ensemble_size=100,
                initial_radius_m=500.0,
                timestep_minutes=15,

                candidate_radius_margin_km=5.0,
                candidate_time_window_hours=2.0,

                synthetic_only=True,
                scenario_id=SCENARIO_ID,
            )

        # -------------------------------------------------------------------
        # Print source estimate
        # -------------------------------------------------------------------

        source_estimate = result.get("source_estimate", {})

        print()
        print("=" * 90)
        print("HINDCAST SOURCE ESTIMATE")
        print("=" * 90)

        print(
            f"Latitude              : "
            f"{source_estimate.get('latitude')}"
        )

        print(
            f"Longitude             : "
            f"{source_estimate.get('longitude')}"
        )

        print(
            f"Radius                : "
            f"{source_estimate.get('radius_km')} km"
        )

        # -------------------------------------------------------------------
        # Release time
        # -------------------------------------------------------------------

        print()
        print("ESTIMATED RELEASE")
        print("-" * 90)

        print(
            f"Estimated release     : "
            f"{result.get('estimated_release_time')}"
        )

        # -------------------------------------------------------------------
        # Candidate information
        # -------------------------------------------------------------------

        candidates = result.get("candidates", [])

        print()
        print("=" * 90)
        print("CANDIDATE RESULTS")
        print("=" * 90)

        print(f"Candidate count       : {result.get('candidate_count', 0)}")

        print()

        if not candidates:
            print("NO CANDIDATES FOUND")

        else:

            print(
                f"{'Rank':<6}"
                f"{'Vessel ID':<22}"
                f"{'Score':>10}"
                f"{'Proximity':>12}"
                f"{'Temporal':>12}"
                f"{'Slowdown':>12}"
                f"{'Loiter':>10}"
                f"{'Approach':>11}"
                f"{'Departure':>12}"
                f"{'Distance':>12}"
            )

            print("-" * 127)

            for rank, candidate in enumerate(candidates, start=1):

                print(
                    f"{rank:<6}"
                    f"{candidate.get('vessel_id', ''):<22}"
                    f"{candidate.get('score', 0):>10.4f}"
                    f"{candidate.get('proximity_score', 0):>12.4f}"
                    f"{candidate.get('temporal_score', 0):>12.4f}"
                    f"{candidate.get('slowdown_score', 0):>12.4f}"
                    f"{candidate.get('loiter_score', 0):>10.4f}"
                    f"{candidate.get('approach_score', 0):>11.4f}"
                    f"{candidate.get('departure_score', 0):>12.4f}"
                    f"{candidate.get('closest_distance_km', 0):>12.4f}"
                )

        # -------------------------------------------------------------------
        # Top prediction
        # -------------------------------------------------------------------

        top_prediction = result.get("top_prediction")

        print()
        print("=" * 90)
        print("ATTRIBUTION RESULT")
        print("=" * 90)

        print(f"True source            : {TRUE_SOURCE}")
        print(f"Top prediction         : {top_prediction}")

        if top_prediction == TRUE_SOURCE:
            print("Top-1 prediction       : PASS")
        else:
            print("Top-1 prediction       : FAIL")

        # -------------------------------------------------------------------
        # Find true source rank
        # -------------------------------------------------------------------

        true_source_rank = None
        true_source_result = None

        for rank, candidate in enumerate(candidates, start=1):

            if candidate.get("vessel_id") == TRUE_SOURCE:
                true_source_rank = rank
                true_source_result = candidate
                break

        print(
            f"True source rank       : "
            f"{true_source_rank if true_source_rank is not None else 'NOT FOUND'}"
        )

        # -------------------------------------------------------------------
        # Score margin
        # -------------------------------------------------------------------

        score_margin = None

        if (
            true_source_result is not None
            and len(candidates) >= 2
        ):

            true_score = true_source_result.get("score", 0.0)

            if true_source_rank == 1:
                runner_up_score = candidates[1].get("score", 0.0)
                score_margin = true_score - runner_up_score

            else:
                top_score = candidates[0].get("score", 0.0)
                score_margin = true_score - top_score

        print(
            f"Score margin          : "
            f"{score_margin if score_margin is not None else 'N/A'}"
        )

        # -------------------------------------------------------------------
        # Final verdict
        # -------------------------------------------------------------------

        print()
        print("=" * 90)
        print("FINAL VERDICT")
        print("=" * 90)

        if top_prediction == TRUE_SOURCE:
            print("SCENARIO-003 ATTRIBUTION: PASS")
        else:
            print("SCENARIO-003 ATTRIBUTION: FAIL")

        print("=" * 90)

    finally:
        weather.close()


if __name__ == "__main__":
    asyncio.run(main())