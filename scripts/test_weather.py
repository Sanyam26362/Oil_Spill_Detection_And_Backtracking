from datetime import datetime, timezone

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

        print("\n")
        print("=" * 70)
        print("DATASET INFORMATION")
        print("=" * 70)

        for key, value in weather.describe().items():
            print(f"{key}: {value}")

        timestamp = datetime(
            2019,
            7,
            15,
            12,
            0,
            tzinfo=timezone.utc,
        )

        latitude = 33.5
        longitude = 34.0

        print("\n")
        print("=" * 70)
        print("ENVIRONMENTAL LOOKUP")
        print("=" * 70)

        print(f"Latitude : {latitude}")
        print(f"Longitude: {longitude}")
        print(f"Time     : {timestamp}")

        env = weather.get_velocity(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
        )

        print("\nERA5 WIND")
        print(f"u10 = {env.wind_u:.6f} m/s")
        print(f"v10 = {env.wind_v:.6f} m/s")

        print("\nCMEMS CURRENT")
        print(f"uo = {env.current_u:.6f} m/s")
        print(f"vo = {env.current_v:.6f} m/s")

        wind_speed = (
            env.wind_u ** 2
            + env.wind_v ** 2
        ) ** 0.5

        current_speed = (
            env.current_u ** 2
            + env.current_v ** 2
        ) ** 0.5

        print("\nMAGNITUDES")
        print(f"Wind speed    = {wind_speed:.6f} m/s")
        print(f"Current speed = {current_speed:.6f} m/s")


if __name__ == "__main__":
    main()