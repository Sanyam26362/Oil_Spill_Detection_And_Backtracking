from datetime import datetime, timezone

import matplotlib.pyplot as plt

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


def main() -> None:

    with WeatherService(
        era5_path=ERA5_FILE,
        cmems_path=CMEMS_FILE,
    ) as weather:

        engine = DriftEngine(
            weather_service=weather,
            windage=0.03,
        )

        trajectory = engine.forward_drift(
            start_latitude=33.5,
            start_longitude=34.0,
            start_time=datetime(
                2019,
                7,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            duration_hours=6,
            timestep_minutes=15,
        )

    latitudes = [
        state.latitude
        for state in trajectory.states
    ]

    longitudes = [
        state.longitude
        for state in trajectory.states
    ]

    plt.figure(figsize=(10, 7))

    plt.plot(
        longitudes,
        latitudes,
        marker="o",
        markersize=3,
    )

    plt.scatter(
        longitudes[0],
        latitudes[0],
        marker="*",
        s=150,
        label="Start",
    )

    plt.scatter(
        longitudes[-1],
        latitudes[-1],
        marker="x",
        s=100,
        label="End",
    )

    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.title("Forward Oil Drift — 15 July 2019")

    plt.grid(True)
    plt.legend()

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()