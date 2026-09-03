"""Shared test fixtures for the oil-spill-backend test suite."""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from datetime import datetime, timezone

os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "raw" / "era5_wind_2019-07-event.nc"
CMEMS_PATH = PROJECT_ROOT / "data" / "ocean" / "raw" / "med_currents_2019-07-event.nc"


@pytest.fixture(scope="session")
def weather_service():
    """Session-scoped WeatherService to avoid re-opening NetCDF files."""
    from app.services.weather_service import WeatherService
    ws = WeatherService(era5_path=ERA5_PATH, cmems_path=CMEMS_PATH)
    yield ws
    ws.close()


@pytest.fixture(scope="session")
def drift_engine(weather_service):
    """Session-scoped DriftEngine."""
    from app.services.drift_engine import DriftEngine
    return DriftEngine(weather_service=weather_service, windage=0.03)


@pytest.fixture(scope="session")
def hindcast_service(drift_engine):
    """Session-scoped HindcastService."""
    from app.services.hindcast_service import HindcastService
    return HindcastService(drift_engine=drift_engine)


@pytest.fixture
def scoring_engine():
    """Fresh ScoringEngine per test."""
    from app.services.scoring_engine import ScoringEngine
    return ScoringEngine()


# Canonical reference point
CANONICAL_LAT = 33.5
CANONICAL_LON = 34.0
CANONICAL_TIME = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

@pytest.fixture(autouse=True)
def reset_db_engine():
    """Ensure global connection pool is disposed after every test to prevent asyncpg 'Event loop is closed' or 'InterfaceError' across async tests."""
    yield
    from app.core.database import engine
    engine.sync_engine.dispose()
    
    # Also clear xarray backend caches to prevent NetCDF: HDF errors on Windows
    try:
        import xarray as xr
        xr.backends.file_manager.FILE_CACHE.clear()
    except Exception:
        pass
