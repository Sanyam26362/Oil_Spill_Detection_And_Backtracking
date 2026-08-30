from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.weather_service import WeatherService


router = APIRouter()


def get_weather_service():
    """
    Provide a year-aware WeatherService.

    The requested timestamp determines which monthly
    ERA5 and CMEMS datasets are loaded.
    """

    project_root = Path(
        __file__
    ).resolve().parents[2]

    weather = WeatherService(
        weather_yearly_dir=(
            project_root
            / "data"
            / "weather"
            / "raw"
            / "yearly"
        ),
        ocean_yearly_dir=(
            project_root
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
    weather: WeatherService = Depends(
        get_weather_service
    ),
):
    return DriftEngine(
        weather_service=weather,
        windage=0.03,
    )


def get_hindcast_service(
    drift_engine: DriftEngine = Depends(
        get_drift_engine
    ),
):
    return HindcastService(
        drift_engine=drift_engine
    )


class ForwardDriftRequest(BaseModel):
    start_latitude: float
    start_longitude: float
    start_time: datetime
    duration_hours: float = Field(
        ...,
        gt=0,
    )


class HindcastDriftRequest(BaseModel):
    obs_latitude: float
    obs_longitude: float
    obs_time: datetime
    duration_hours: float = Field(
        ...,
        gt=0,
    )
    ensemble_size: int = Field(
        100,
        gt=0,
    )


@router.post(
    "/forward",
    status_code=status.HTTP_200_OK,
)
async def forward_drift(
    request: ForwardDriftRequest,
    drift_engine: DriftEngine = Depends(
        get_drift_engine
    ),
):
    try:
        trajectory = (
            drift_engine.forward_drift(
                start_latitude=(
                    request.start_latitude
                ),
                start_longitude=(
                    request.start_longitude
                ),
                start_time=(
                    request.start_time
                ),
                duration_hours=(
                    request.duration_hours
                ),
            )
        )

        return {
            "end_latitude": (
                trajectory.end.latitude
            ),
            "end_longitude": (
                trajectory.end.longitude
            ),
            "end_timestamp": (
                trajectory.end.timestamp
            ),
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
    hindcast_service: HindcastService = Depends(
        get_hindcast_service
    ),
):
    try:
        estimate = (
            hindcast_service.backward_ensemble(
                obs_latitude=(
                    request.obs_latitude
                ),
                obs_longitude=(
                    request.obs_longitude
                ),
                obs_time=(
                    request.obs_time
                ),
                duration_hours=(
                    request.duration_hours
                ),
                ensemble_size=(
                    request.ensemble_size
                ),
            )
        )

        return {
            "centroid_latitude": (
                estimate.centroid_latitude
            ),
            "centroid_longitude": (
                estimate.centroid_longitude
            ),
            "radius_km": (
                estimate.radius_km
            ),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc