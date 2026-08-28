from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService

router = APIRouter()

def get_weather_service():
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    weather = WeatherService(
        era5_path=PROJECT_ROOT / "data/weather/raw/era5_wind_2019-07-event.nc",
        cmems_path=PROJECT_ROOT / "data/ocean/raw/med_currents_2019-07-event.nc"
    )
    weather.__enter__()
    return weather

def get_attribution_engine(weather: WeatherService = Depends(get_weather_service)):
    return AttributionEngine(weather_service=weather)

class AttributionRequest(BaseModel):
    observation_latitude: float
    observation_longitude: float
    observation_time: datetime
    drift_duration_hours: float = Field(..., gt=0)
    synthetic_only: Optional[bool] = None
    scenario_id: Optional[str] = None

@router.post("", status_code=status.HTTP_200_OK)
async def attribute_spill(
    request: AttributionRequest,
    db: AsyncSession = Depends(get_db),
    engine: AttributionEngine = Depends(get_attribution_engine)
):
    try:
        result = await engine.attribute(
            db=db,
            observation_latitude=request.observation_latitude,
            observation_longitude=request.observation_longitude,
            observation_time=request.observation_time,
            drift_duration_hours=request.drift_duration_hours,
            synthetic_only=request.synthetic_only,
            scenario_id=request.scenario_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
