from datetime import datetime, timezone
from pathlib import Path

from app.services.weather_service import WeatherService


# Project root:
# D:\projects\oil-spill-backend
project_root = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Create environmental data service
# ---------------------------------------------------------------------------

weather = WeatherService(
    weather_yearly_dir=project_root / "data" / "weather" / "raw" / "yearly",
    ocean_yearly_dir=project_root / "data" / "ocean" / "raw" / "yearly",
)


try:
    # -----------------------------------------------------------------------
    # Scenario-002 observation
    # -----------------------------------------------------------------------
    latitude = 33.48090362468654
    longitude = 34.03963561414212

    timestamp = datetime(
        2019,
        7,
        15,
        18,
        0,
        0,
        tzinfo=timezone.utc,
    )

    print("=" * 80)
    print("SCENARIO-002 ENVIRONMENT TEST")
    print("=" * 80)

    print(f"Latitude  : {latitude}")
    print(f"Longitude : {longitude}")
    print(f"Time      : {timestamp}")

    print()
    print("Querying environmental data...")
    print()

    # -----------------------------------------------------------------------
    # Environmental lookup
    # -----------------------------------------------------------------------
    result = weather.get_environment(
        latitude=latitude,
        longitude=longitude,
        timestamp=timestamp,
    )

    # -----------------------------------------------------------------------
    # Print result
    # -----------------------------------------------------------------------
    print("=" * 80)
    print("ENVIRONMENTAL RESULT")
    print("=" * 80)

    print(result)

    print()
    print("=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)

finally:
    # -----------------------------------------------------------------------
    # Close datasets / resources
    # -----------------------------------------------------------------------
    weather.close()
    