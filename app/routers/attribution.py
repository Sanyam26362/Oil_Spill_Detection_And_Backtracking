from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


router = APIRouter()


def get_weather_service():
    """
    Provide a year-aware WeatherService.

    The service selects the appropriate 2019 monthly
    ERA5/CMEMS dataset from the request timestamp.
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


def get_attribution_engine(
    weather: WeatherService = Depends(
        get_weather_service
    ),
):
    return AttributionEngine(
        weather_service=weather
    )


class AttributionRequest(BaseModel):
    observation_latitude: float
    observation_longitude: float
    observation_time: datetime
    drift_duration_hours: float = Field(
        ...,
        gt=0,
    )
    synthetic_only: Optional[bool] = None
    scenario_id: Optional[str] = None


@router.post(
    "",
    status_code=status.HTTP_200_OK,
)
async def attribute_spill(
    request: AttributionRequest,
    db: AsyncSession = Depends(get_db),
    engine: AttributionEngine = Depends(
        get_attribution_engine
    ),
):
    try:
        result = await engine.attribute(
            db=db,
            observation_latitude=(
                request.observation_latitude
            ),
            observation_longitude=(
                request.observation_longitude
            ),
            observation_time=(
                request.observation_time
            ),
            drift_duration_hours=(
                request.drift_duration_hours
            ),
            synthetic_only=(
                request.synthetic_only
            ),
            scenario_id=(
                request.scenario_id
            ),
        )

        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc