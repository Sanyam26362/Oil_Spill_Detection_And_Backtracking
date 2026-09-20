from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


router = APIRouter()


def get_weather_service(request: Request):
    """
    D2: Return the single WeatherService from app.state,
    created once at application startup.
    """
    return request.app.state.weather_service


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

    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc