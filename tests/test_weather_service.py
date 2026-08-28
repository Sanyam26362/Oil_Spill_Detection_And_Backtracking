"""Tests for WeatherService."""
import pytest
import numpy as np
from datetime import datetime, timezone

from tests.conftest import CANONICAL_LAT, CANONICAL_LON, CANONICAL_TIME


class TestWeatherServiceLookup:
    """Validate known environmental data lookups."""

    def test_known_era5_wind(self, weather_service):
        """ERA5 lookup at canonical point should match verified values."""
        vel = weather_service.get_velocity(
            latitude=CANONICAL_LAT,
            longitude=CANONICAL_LON,
            timestamp=CANONICAL_TIME,
        )
        # Verified: u10 ≈ 6.39, v10 ≈ 1.35
        assert abs(vel.wind_u - 6.392639) < 0.01, f"wind_u={vel.wind_u}"
        assert abs(vel.wind_v - 1.347672) < 0.01, f"wind_v={vel.wind_v}"

    def test_known_cmems_current(self, weather_service):
        """CMEMS lookup at canonical point should match verified values."""
        vel = weather_service.get_velocity(
            latitude=CANONICAL_LAT,
            longitude=CANONICAL_LON,
            timestamp=CANONICAL_TIME,
        )
        # Verified: uo ≈ 0.027, vo ≈ -0.091
        assert abs(vel.current_u - 0.027409) < 0.01, f"current_u={vel.current_u}"
        assert abs(vel.current_v - (-0.090901)) < 0.01, f"current_v={vel.current_v}"

    def test_no_nan_at_valid_point(self, weather_service):
        """All 4 components should be non-NaN at valid point."""
        vel = weather_service.get_velocity(
            latitude=CANONICAL_LAT,
            longitude=CANONICAL_LON,
            timestamp=CANONICAL_TIME,
        )
        assert not np.isnan(vel.wind_u)
        assert not np.isnan(vel.wind_v)
        assert not np.isnan(vel.current_u)
        assert not np.isnan(vel.current_v)

    def test_invalid_latitude_raises(self, weather_service):
        """Out-of-range latitude should raise ValueError."""
        with pytest.raises(ValueError):
            weather_service.get_velocity(
                latitude=91.0,
                longitude=CANONICAL_LON,
                timestamp=CANONICAL_TIME,
            )


class TestWeatherServiceDescribe:
    """Test the describe() diagnostic method."""

    def test_describe_returns_dict(self, weather_service):
        desc = weather_service.describe()
        assert "era5_dimensions" in desc
        assert "cmems_dimensions" in desc
        assert "era5_variables" in desc
        assert "cmems_variables" in desc
