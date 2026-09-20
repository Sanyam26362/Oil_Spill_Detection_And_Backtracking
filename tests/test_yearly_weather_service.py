import pytest
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

@pytest.fixture(autouse=True)
def check_yearly_datasets():
    if not WEATHER_DIR.exists() or not any(WEATHER_DIR.glob("*.nc")):
        pytest.skip("Yearly environmental NetCDF datasets not present in this environment")

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


def test_month_alternation_lru_cache():
    """
    C3: Assert that requesting two different months in immediate alternation
    returns correct non-corrupted values, and that the previously-loaded month
    is still cached (not reloaded from disk) on the third request.
    """
    service = WeatherService(
        weather_yearly_dir=WEATHER_DIR,
        ocean_yearly_dir=OCEAN_DIR,
        cache_max_months=3,
    )

    load_count = 0
    orig_load = service._load_single_month

    def spy_load(year: int, month: int):
        nonlocal load_count
        load_count += 1
        return orig_load(year, month)

    service._load_single_month = spy_load

    try:
        # Request 1: Month 1 (January 2019)
        v1 = service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(2019, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
        assert np.isfinite(v1.wind_u)
        assert np.isfinite(v1.wind_v)
        assert np.isfinite(v1.current_u)
        assert np.isfinite(v1.current_v)
        assert load_count == 1
        assert service.describe()["loaded_month"] == 1
        assert len(service._month_cache) == 1

        # Request 2: Month 2 (February 2019) - alternating
        v2 = service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(2019, 2, 15, 12, 0, tzinfo=timezone.utc),
        )
        assert np.isfinite(v2.wind_u)
        assert np.isfinite(v2.wind_v)
        assert np.isfinite(v2.current_u)
        assert np.isfinite(v2.current_v)
        assert load_count == 2
        assert service.describe()["loaded_month"] == 2
        assert len(service._month_cache) == 2

        # Request 3: Month 1 AGAIN - must be served from cache without reloading!
        v3 = service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(2019, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
        # Check values match Request 1 exactly
        assert v3.wind_u == v1.wind_u
        assert v3.wind_v == v1.wind_v
        assert v3.current_u == v1.current_u
        assert v3.current_v == v1.current_v

        # Load count must NOT have increased
        assert load_count == 2, f"Expected 2 loads (from disk), but got {load_count} (cache thrashing detected)"
        assert service.describe()["loaded_month"] == 1
        assert len(service._month_cache) == 2

    finally:
        service.close()


def test_cross_month_concat_caching_and_lru_eviction():
    """
    E1: Assert that cross-month concat datasets are cached and invalidated
    upon eviction of an underlying month from the LRU.
    """
    service = WeatherService(
        weather_yearly_dir=WEATHER_DIR,
        ocean_yearly_dir=OCEAN_DIR,
        cache_max_months=2,
    )

    try:
        # Request at month boundary: 2019-01-31 23:55:00
        # Triggers cross-month loading of Jan and Feb into LRU
        boundary_ts = datetime(2019, 1, 31, 23, 55, 0, tzinfo=timezone.utc)
        v1 = service.get_velocity(latitude=35.0, longitude=24.0, timestamp=boundary_ts)
        assert np.isfinite(v1.wind_u)
        assert (2019, 1) in service._cross_month_cache

        cached_era5, cached_cmems = service._cross_month_cache[(2019, 1)]

        # Second request near same boundary must reuse the exact cached xr.concat dataset
        v2 = service.get_velocity(latitude=35.0, longitude=24.0, timestamp=boundary_ts)
        assert v2.wind_u == v1.wind_u
        assert service._cross_month_cache[(2019, 1)][0] is cached_era5

        # Active month must remain the requested month (January = 1)
        assert service.describe()["loaded_month"] == 1

        # Now request month 3 (March 2019), exceeding cache_max_months=2
        # This will evict the LRU month (which is February = 2)
        service.get_velocity(
            latitude=35.0,
            longitude=24.0,
            timestamp=datetime(2019, 3, 15, 12, 0, tzinfo=timezone.utc),
        )
        assert len(service._month_cache) <= 2
        # Cross-month cache for (2019, 1) depended on month 2, so it must be invalidated
        assert (2019, 1) not in service._cross_month_cache

    finally:
        service.close()