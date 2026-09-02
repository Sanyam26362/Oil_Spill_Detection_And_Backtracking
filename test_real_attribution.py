import asyncio

from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


async def main():

    print("=" * 100)
    print("REAL AIS VESSEL ATTRIBUTION TEST")
    print("=" * 100)

    weather = WeatherService(
        weather_yearly_dir="data/weather/raw/yearly",
        ocean_yearly_dir="data/ocean/raw/yearly",
    )

    engine = AttributionEngine(
        weather_service=weather
    )

    # Use the first real detection from our
    # exhaustive environmental test.
    observation_latitude = 35.05
    observation_longitude = 24.0467
    observation_time = datetime(
        2019,
        4,
        11,
        15,
        47,
        46,
        tzinfo=timezone.utc,
    )

    print()
    print("OBSERVATION")
    print("-" * 100)
    print("Latitude :", observation_latitude)
    print("Longitude:", observation_longitude)
    print("Time     :", observation_time)

    try:

        async with AsyncSessionLocal() as db:

            result = await engine.attribute(
                db=db,
                observation_latitude=observation_latitude,
                observation_longitude=observation_longitude,
                observation_time=observation_time,
                drift_duration_hours=6,
                ensemble_size=100,
                initial_radius_m=500,
                timestep_minutes=15,

                # Search synthetic AIS data.
                synthetic_only=True,

                # IMPORTANT:
                # Replace this if your synthetic AIS
                # was generated with a specific scenario_id.
                scenario_id=None,
            )

        print()
        print("=" * 100)
        print("ATTRIBUTION RESULT")
        print("=" * 100)

        print()
        print("Source estimate:")
        print(
            "  Latitude :",
            result["source_estimate"]["latitude"],
        )
        print(
            "  Longitude:",
            result["source_estimate"]["longitude"],
        )
        print(
            "  Radius   :",
            result["source_estimate"]["radius_km"],
            "km",
        )

        print()
        print(
            "Estimated release time:",
            result.get("estimated_release_time"),
        )

        print()
        print(
            "Candidate count:",
            result["candidate_count"],
        )

        print()
        print("Candidates:")

        if not result["candidates"]:

            print("  NO CANDIDATES FOUND")

        else:

            for i, candidate in enumerate(
                result["candidates"],
                start=1,
            ):

                print()
                print(f"  #{i}")
                print(
                    "    Vessel ID:",
                    candidate["vessel_id"],
                )
                print(
                    "    Total score:",
                    candidate["score"],
                )
                print(
                    "    Proximity:",
                    candidate["proximity_score"],
                )
                print(
                    "    Temporal:",
                    candidate["temporal_score"],
                )
                print(
                    "    Slowdown:",
                    candidate["slowdown_score"],
                )
                print(
                    "    Loiter:",
                    candidate["loiter_score"],
                )
                print(
                    "    Approach:",
                    candidate["approach_score"],
                )
                print(
                    "    Departure:",
                    candidate["departure_score"],
                )
                print(
                    "    Closest distance:",
                    candidate["closest_distance_km"],
                    "km",
                )
                print(
                    "    Minimum event speed:",
                    candidate[
                        "minimum_event_speed_knots"
                    ],
                    "knots",
                )

        print()
        print("Top prediction:")
        print(
            " ",
            result.get("top_prediction"),
        )

        print()
        print("=" * 100)
        print("STATUS: PASS")
        print("=" * 100)

    except Exception as exc:

        print()
        print("=" * 100)
        print("STATUS: FAIL")
        print("=" * 100)

        print(
            type(exc).__name__,
            ":",
            str(exc),
        )

    finally:

        weather.close()


if __name__ == "__main__":
    asyncio.run(main())
