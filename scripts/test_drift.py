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

        print()
        print("=" * 80)
        print("FORWARD OIL DRIFT TEST")
        print("=" * 80)

        print(
            f"Start position: "
            f"33.500000, 34.000000"
        )

        print(
            f"Windage: {engine.windage}"
        )

        print()

        for state in trajectory.states:

            print(
                f"{state.timestamp} | "
                f"lat={state.latitude:.6f} | "
                f"lon={state.longitude:.6f} | "
                f"drift_u={state.drift_u:.6f} | "
                f"drift_v={state.drift_v:.6f}"
            )

        if trajectory.states:

            first = trajectory.states[0]
            last = trajectory.states[-1]

            print()
            print("=" * 80)
            print("TRAJECTORY SUMMARY")
            print("=" * 80)

            print(
                f"Initial: "
                f"{first.latitude:.6f}, "
                f"{first.longitude:.6f}"
            )

            print(
                f"Final:   "
                f"{last.latitude:.6f}, "
                f"{last.longitude:.6f}"
            )

            print(
                f"Latitude change: "
                f"{last.latitude - first.latitude:.6f}°"
            )

            print(
                f"Longitude change: "
                f"{last.longitude - first.longitude:.6f}°"
            )

            print(
                f"Number of steps: "
                f"{len(trajectory.states)}"
            )


if __name__ == "__main__":
    main()