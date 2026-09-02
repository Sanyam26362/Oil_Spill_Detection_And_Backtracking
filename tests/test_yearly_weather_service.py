from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.services.weather_service import WeatherService


PROJECT_ROOT = Path(__file__).resolve().parents[1]

WEATHER_DIR = (
    PROJECT_ROOT
    / "data"
    / "weather"
    / "raw"
    / "yearly"
)

OCEAN_DIR = (
    PROJECT_ROOT
    / "data"
    / "ocean"
    / "raw"
    / "yearly"
)


def make_service():
    return WeatherService(
        weather_yearly_dir=WEATHER_DIR,
        ocean_yearly_dir=OCEAN_DIR,
    )


def test_january_lookup():
    service = make_service()

    try:
        velocity = service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(
                2019,
                1,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert np.isfinite(velocity.wind_u)
        assert np.isfinite(velocity.wind_v)
        assert np.isfinite(velocity.current_u)
        assert np.isfinite(velocity.current_v)

        info = service.describe()

        assert info["loaded_year"] == 2019
        assert info["loaded_month"] == 1

    finally:
        service.close()


def test_july_lookup():
    service = make_service()

    try:
        velocity = service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(
                2019,
                7,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert np.isfinite(velocity.wind_u)
        assert np.isfinite(velocity.wind_v)
        assert np.isfinite(velocity.current_u)
        assert np.isfinite(velocity.current_v)

        info = service.describe()

        assert info["loaded_year"] == 2019
        assert info["loaded_month"] == 7

    finally:
        service.close()


def test_december_lookup():
    service = make_service()

    try:
        velocity = service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(
                2019,
                12,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert np.isfinite(velocity.wind_u)
        assert np.isfinite(velocity.wind_v)
        assert np.isfinite(velocity.current_u)
        assert np.isfinite(velocity.current_v)

        info = service.describe()

        assert info["loaded_year"] == 2019
        assert info["loaded_month"] == 12

    finally:
        service.close()


def test_month_switching():
    service = make_service()

    try:
        service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(
                2019,
                1,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert (
            service.describe()["loaded_month"]
            == 1
        )

        service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(
                2019,
                2,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert (
            service.describe()["loaded_month"]
            == 2
        )

        service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(
                2019,
                7,
                15,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        assert (
            service.describe()["loaded_month"]
            == 7
        )

    finally:
        service.close()


def test_vectorized_lookup():
    service = make_service()

    try:
        wind_u, wind_v, current_u, current_v = (
            service.get_velocities(
                latitudes=np.array(
                    [34.8, 35.0, 34.9]
                ),
                longitudes=np.array(
                    [23.8, 24.0, 24.1]
                ),
                timestamp=datetime(
                    2019,
                    7,
                    15,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            )
        )

        assert wind_u.shape == (3,)
        assert wind_v.shape == (3,)
        assert current_u.shape == (3,)
        assert current_v.shape == (3,)

        assert np.all(
            np.isfinite(wind_u)
        )
        assert np.all(
            np.isfinite(wind_v)
        )
        assert np.all(
            np.isfinite(current_u)
        )
        assert np.all(
            np.isfinite(current_v)
        )

    finally:
        service.close()


def test_missing_month_fails_cleanly():
    service = make_service()

    try:
        try:
            service.get_velocity(
                latitude=33.5,
                longitude=34.0,
                timestamp=datetime(
                    2020,
                    1,
                    15,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            )
        except FileNotFoundError as exc:
            assert (
                "2020-01" in str(exc)
            )
        else:
            raise AssertionError(
                "Expected missing environmental "
                "data to raise FileNotFoundError."
            )

    finally:
        service.close()