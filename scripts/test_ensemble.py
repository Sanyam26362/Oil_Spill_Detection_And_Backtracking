from datetime import datetime, timezone

from app.services.drift_engine import DriftEngine
from app.services.weather_service import WeatherService
from app.services.hindcast_service import HindcastService


ERA5_FILE = (
    "data/weather/raw/"
    "era5_wind_2019-07-event.nc"
)

CMEMS_FILE = (
    "data/ocean/raw/"
    "med_currents_2019-07-event.nc"
)


def main() -> None:

    source_latitude = 33.5
    source_longitude = 34.0

    source_time = datetime(
        2019,
        7,
        15,
        12,
        0,
        tzinfo=timezone.utc,
    )

    # Generate a synthetic observation using the forward model.
    with WeatherService(
        era5_path=ERA5_FILE,
        cmems_path=CMEMS_FILE,
    ) as weather:

        engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        forward = engine.forward_drift(
            start_latitude=source_latitude,
            start_longitude=source_longitude,
            start_time=source_time,
            duration_hours=6,
            timestep_minutes=15,
        )

        observation = forward.end

        print()
        print("=" * 80)
        print("SYNTHETIC OBSERVATION")
        print("=" * 80)

        print(
            f"Latitude : {observation.latitude:.6f}"
        )

        print(
            f"Longitude: {observation.longitude:.6f}"
        )

        print(
            f"Time     : {observation.timestamp}"
        )

        # ----------------------------------------------------------
        # Backward ensemble
        # ----------------------------------------------------------

        hindcast = HindcastService(drift_engine=engine)
        estimate = hindcast.backward_ensemble(
            obs_latitude=observation.latitude,
            obs_longitude=observation.longitude,
            obs_time=observation.timestamp,
            duration_hours=6,
            ensemble_size=100,
            initial_radius_m=500,
            timestep_minutes=15,
        )

    print()
    print("=" * 80)
    print("BACKWARD ENSEMBLE")
    print("=" * 80)

    print(
        f"Particles requested : 100"
    )

    print(
        f"Particles recovered : "
        f"{len(estimate.particles)}"
    )

    print(
        f"Source centroid     : "
        f"{estimate.centroid_latitude:.6f}, "
        f"{estimate.centroid_longitude:.6f}"
    )

    print(
        f"Source radius       : "
        f"{estimate.radius_km:.3f} km"
    )

    print()
    print("TRUE SOURCE")
    print("-" * 80)

    print(
        f"{source_latitude:.6f}, "
        f"{source_longitude:.6f}"
    )

    error = engine.haversine_km(
        source_latitude,
        source_longitude,
        estimate.centroid_latitude,
        estimate.centroid_longitude,
    )

    print()
    print(
        f"Centroid error from true source: "
        f"{error:.3f} km"
    )


if __name__ == "__main__":
    main()