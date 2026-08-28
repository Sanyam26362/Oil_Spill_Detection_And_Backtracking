from datetime import datetime, timezone

import matplotlib.pyplot as plt

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

        hindcast = HindcastService(
            drift_engine=drift_engine,
        )

        # Generate controlled observation.
        forward = drift_engine.forward_drift(
            start_latitude=source_latitude,
            start_longitude=source_longitude,
            start_time=source_time,
            duration_hours=6,
            timestep_minutes=15,
        )

        observation = forward.end

        # Run backward ensemble.
        estimate = hindcast.backward_ensemble(
            obs_latitude=observation.latitude,
            obs_longitude=observation.longitude,
            obs_time=observation.timestamp,
            duration_hours=6,
            ensemble_size=500,
            initial_radius_m=500,
            timestep_minutes=15,
            random_seed=42,
        )

        density = hindcast.build_density_grid(
            estimate,
            grid_size=75,
        )

    # --------------------------------------------------------------
    # Plot recovered particles.
    # --------------------------------------------------------------

    particle_latitudes = [
        particle.latitude
        for particle in estimate.particles
    ]

    particle_longitudes = [
        particle.longitude
        for particle in estimate.particles
    ]

    plt.figure(figsize=(10, 8))

    plt.scatter(
        particle_longitudes,
        particle_latitudes,
        s=8,
        alpha=0.6,
        label="Recovered particles",
    )

    plt.scatter(
        source_longitude,
        source_latitude,
        marker="*",
        s=200,
        label="True source",
    )

    plt.scatter(
        observation.longitude,
        observation.latitude,
        marker="x",
        s=120,
        label="Observed slick",
    )

    plt.scatter(
        estimate.centroid_longitude,
        estimate.centroid_latitude,
        marker="+",
        s=150,
        label="Source centroid",
    )

    plt.xlabel("Longitude")
    plt.ylabel("Latitude")

    plt.title(
        "Backward Hindcast Source Ensemble"
    )

    plt.grid(True)
    plt.legend()

    plt.tight_layout()
    plt.show()

    # --------------------------------------------------------------
    # Plot density.
    # --------------------------------------------------------------

    plt.figure(figsize=(10, 8))

    plt.pcolormesh(
        density.longitudes,
        density.latitudes,
        density.density,
        shading="auto",
    )

    plt.scatter(
        source_longitude,
        source_latitude,
        marker="*",
        s=200,
        label="True source",
    )

    plt.scatter(
        estimate.centroid_longitude,
        estimate.centroid_latitude,
        marker="+",
        s=150,
        label="Source centroid",
    )

    plt.xlabel("Longitude")
    plt.ylabel("Latitude")

    plt.title(
        "Backward Hindcast Source Density"
    )

    plt.colorbar(
        label="Particle probability",
    )

    plt.grid(True)
    plt.legend()

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()