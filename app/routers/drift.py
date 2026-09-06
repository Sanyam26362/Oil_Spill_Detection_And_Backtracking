from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.weather_service import WeatherService


router = APIRouter()

# ----------------------------------------------------------------------
# Project Path Resolution & Diagnostic Plot Cache
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLOT_MAP_PATH = PROJECT_ROOT / "json_output" / "validation" / "diagnostic_plot_urls.json"

_plot_urls_cache: dict[str, str] | None = None


def _get_diagnostic_plot_url(spill_id: str) -> str | None:
    """Retrieve the Cloudinary URL for a spill with in-memory caching and auto-refresh."""
    global _plot_urls_cache
    if _plot_urls_cache is None:
        _plot_urls_cache = {}
        if PLOT_MAP_PATH.exists():
            try:
                with open(PLOT_MAP_PATH, "r", encoding="utf-8") as f:
                    _plot_urls_cache = json.load(f)
            except Exception:
                _plot_urls_cache = {}

    url = _plot_urls_cache.get(spill_id)

    # If not found in cache, check disk once in case the JSON was recently updated
    if not url and PLOT_MAP_PATH.exists():
        try:
            with open(PLOT_MAP_PATH, "r", encoding="utf-8") as f:
                _plot_urls_cache = json.load(f)
                url = _plot_urls_cache.get(spill_id)
        except Exception:
            pass

    return url


# ----------------------------------------------------------------------
# Dependency Providers
# ----------------------------------------------------------------------
def get_weather_service():
    """
    Provide a year-aware WeatherService.

    The requested timestamp determines which monthly
    ERA5 and CMEMS datasets are loaded.
    """
    weather = WeatherService(
        weather_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "weather"
            / "raw"
            / "yearly"
        ),
        ocean_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "ocean"
            / "raw"
            / "yearly"
        ),
    )

    try:
        yield weather
    finally:
        weather.close()


def get_drift_engine(
    weather: WeatherService = Depends(get_weather_service),
):
    return DriftEngine(
        weather_service=weather,
        windage=0.03,
    )


def get_hindcast_service(
    drift_engine: DriftEngine = Depends(get_drift_engine),
):
    return HindcastService(drift_engine=drift_engine)


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------
class ForwardDriftRequest(BaseModel):
    start_latitude: float
    start_longitude: float
    start_time: datetime
    duration_hours: float = Field(..., gt=0)


class HindcastDriftRequest(BaseModel):
    obs_latitude: float
    obs_longitude: float
    obs_time: datetime
    duration_hours: float = Field(..., gt=0)
    ensemble_size: int = Field(100, gt=0)


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@router.post(
    "/forward",
    status_code=status.HTTP_200_OK,
)
async def forward_drift(
    request: ForwardDriftRequest,
    drift_engine: DriftEngine = Depends(get_drift_engine),
):
    try:
        trajectory = drift_engine.forward_drift(
            start_latitude=request.start_latitude,
            start_longitude=request.start_longitude,
            start_time=request.start_time,
            duration_hours=request.duration_hours,
        )

        return {
            "end_latitude": trajectory.end.latitude,
            "end_longitude": trajectory.end.longitude,
            "end_timestamp": trajectory.end.timestamp,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/hindcast",
    status_code=status.HTTP_200_OK,
)
async def hindcast_drift(
    request: HindcastDriftRequest,
    hindcast_service: HindcastService = Depends(get_hindcast_service),
):
    try:
        estimate = hindcast_service.backward_ensemble(
            obs_latitude=request.obs_latitude,
            obs_longitude=request.obs_longitude,
            obs_time=request.obs_time,
            duration_hours=request.duration_hours,
            ensemble_size=request.ensemble_size,
        )

        return {
            "centroid_latitude": estimate.centroid_latitude,
            "centroid_longitude": estimate.centroid_longitude,
            "radius_km": estimate.radius_km,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/{spill_id}/diagnostic-plot",
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/diagnostic-plot/{spill_id}",
    status_code=status.HTTP_200_OK,
)
async def get_spill_diagnostic_plot(spill_id: str):
    """
    Retrieve the Cloudinary-hosted diagnostic SAR polygon plot
    for a given spill ID.
    """
    plot_url = _get_diagnostic_plot_url(spill_id)

    if not plot_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnostic plot not found for spill '{spill_id}'",
        )

    return {
        "spill_id": spill_id,
        "diagnostic_plot_url": plot_url,
    }