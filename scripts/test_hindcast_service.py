from datetime import datetime, timezone

from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.weather_service import WeatherService


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

    with WeatherService(
        era5_path=ERA5_FILE,
        cmems_path=CMEMS_FILE,
    ) as weather:

        drift_engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        hindcast_service = HindcastService(
            drift_engine=drift_engine,
        )

        # ----------------------------------------------------------
        # Generate a controlled synthetic observation.
        # ----------------------------------------------------------

        forward = drift_engine.forward_drift(
            start_latitude=source_latitude,
            start_longitude=source_longitude,
            start_time=source_time,
            duration_hours=6,
            timestep_minutes=15,
        )

        observation = forward.end

        print()
        print("=" * 80)
        print("CONTROLLED OBSERVATION")
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
        # Run backward ensemble.
        # ----------------------------------------------------------

        estimate = hindcast_service.backward_ensemble(
            obs_latitude=observation.latitude,
            obs_longitude=observation.longitude,
            obs_time=observation.timestamp,
            duration_hours=6,
            ensemble_size=100,
            initial_radius_m=500,
            timestep_minutes=15,
            random_seed=42,
        )

        print()
        print("=" * 80)
        print("HINDCAST SOURCE ESTIMATE")
        print("=" * 80)

        print(
            f"Particles recovered : "
            f"{len(estimate.particles)}"
        )

        print(
            f"Centroid             : "
            f"{estimate.centroid_latitude:.6f}, "
            f"{estimate.centroid_longitude:.6f}"
        )

        print(
            f"Radius               : "
            f"{estimate.radius_km:.3f} km"
        )

        # ----------------------------------------------------------
        # Compare against known source.
        # ----------------------------------------------------------

        error = hindcast_service.haversine_km(
            source_latitude,
            source_longitude,
            estimate.centroid_latitude,
            estimate.centroid_longitude,
        )

        print()
        print("=" * 80)
        print("SOURCE RECOVERY")
        print("=" * 80)

        print(
            f"True source          : "
            f"{source_latitude:.6f}, "
            f"{source_longitude:.6f}"
        )

        print(
            f"Centroid error       : "
            f"{error:.3f} km"
        )

        # ----------------------------------------------------------
        # Build density grid.
        # ----------------------------------------------------------

        density = hindcast_service.build_density_grid(
            estimate,
            grid_size=50,
        )

        print()
        print("=" * 80)
        print("SOURCE DENSITY GRID")
        print("=" * 80)

        print(
            f"Grid shape           : "
            f"{density.density.shape}"
        )

        print(
            f"Total probability    : "
            f"{density.density.sum():.6f}"
        )

        print(
            f"Maximum cell density : "
            f"{density.density.max():.6f}"
        )


if __name__ == "__main__":
    main()