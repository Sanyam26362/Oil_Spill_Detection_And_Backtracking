from datetime import datetime, timezone

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


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate great-circle distance between two coordinates.
    """

    from math import (
        atan2,
        cos,
        radians,
        sin,
        sqrt,
    )

    earth_radius_km = 6371.0

    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1_rad)
        * cos(lat2_rad)
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a),
    )

    return earth_radius_km * c


def main() -> None:

    source_lat = 33.5
    source_lon = 34.0

    source_time = datetime(
        2019,
        7,
        15,
        12,
        0,
        tzinfo=timezone.utc,
    )

    duration_hours = 6
    timestep_minutes = 15

    with WeatherService(
        era5_path=ERA5_FILE,
        cmems_path=CMEMS_FILE,
    ) as weather:

        engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        # ==========================================================
        # 1. FORWARD DRIFT
        # ==========================================================

        forward = engine.forward_drift(
            start_latitude=source_lat,
            start_longitude=source_lon,
            start_time=source_time,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
        )

        observation = forward.end

        # ==========================================================
        # 2. BACKWARD HINDCAST
        # ==========================================================

        backward = engine.backward_drift(
            obs_latitude=observation.latitude,
            obs_longitude=observation.longitude,
            obs_time=observation.timestamp,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
        )

        recovered = backward.end

    # ==============================================================
    # 3. ERROR
    # ==============================================================

    recovery_error_km = haversine_km(
        source_lat,
        source_lon,
        recovered.latitude,
        recovered.longitude,
    )

    print()
    print("=" * 80)
    print("FORWARD → BACKWARD HINDCAST VALIDATION")
    print("=" * 80)

    print()
    print("TRUE SOURCE")
    print("-" * 80)

    print(f"Latitude : {source_lat:.6f}")
    print(f"Longitude: {source_lon:.6f}")
    print(f"Time     : {source_time}")

    print()
    print("SYNTHETIC OBSERVATION")
    print("-" * 80)

    print(
        f"Latitude : "
        f"{observation.latitude:.6f}"
    )

    print(
        f"Longitude: "
        f"{observation.longitude:.6f}"
    )

    print(
        f"Time     : "
        f"{observation.timestamp}"
    )

    print()
    print("HINDCAST RESULT")
    print("-" * 80)

    print(
        f"Latitude : "
        f"{recovered.latitude:.6f}"
    )

    print(
        f"Longitude: "
        f"{recovered.longitude:.6f}"
    )

    print(
        f"Time     : "
        f"{recovered.timestamp}"
    )

    print()
    print("RECOVERY ERROR")
    print("-" * 80)

    print(
        f"Source recovery error: "
        f"{recovery_error_km:.3f} km"
    )

    print()

    # We aren't imposing a scientific pass/fail threshold yet.
    # This first test is for understanding numerical behavior.

    print(
        "This is a numerical consistency test, "
        "not yet a real-world hindcast accuracy metric."
    )


if __name__ == "__main__":
    main()