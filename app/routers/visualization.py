from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.visualization import VisualizationResponse
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.visualization_service import VisualizationService
from app.services.weather_service import WeatherService


router = APIRouter()


def get_weather_service(request: Request):
    """
    D2: Return the single WeatherService from app.state,
    created once at application startup.
    """
    return request.app.state.weather_service


def shutdown_weather_service():
    """
    D2: No-op-safe stub kept for backwards compatibility.
    The weather service lifecycle is now managed in main.py lifespan.
    """
    pass


def get_drift_engine(
    weather: WeatherService = Depends(
        get_weather_service
    ),
) -> DriftEngine:
    return DriftEngine(
        weather_service=weather,
        windage=0.03,
    )


def get_hindcast_service(
    drift_engine: DriftEngine = Depends(
        get_drift_engine
    ),
) -> HindcastService:
    return HindcastService(
        drift_engine=drift_engine,
    )


def get_visualization_service(
    drift_engine: DriftEngine = Depends(
        get_drift_engine
    ),
    hindcast_service: HindcastService = Depends(
        get_hindcast_service
    ),
) -> VisualizationService:
    return VisualizationService(
        drift_engine=drift_engine,
        hindcast_service=hindcast_service,
    )


@router.get(
    "/spills/{spill_id}",
    response_model=VisualizationResponse,
    status_code=status.HTTP_200_OK,
)
def get_spill_visualization(
    spill_id: str,
    service: VisualizationService = Depends(
        get_visualization_service
    ),
):
    """
    Return frontend-ready visualization data for a demo spill.

    Includes:

    - spill detection point
    - detection timestamp
    - hindcast source estimate
    - wind at detection point
    - ocean current at detection point
    - complete backward trajectory
    """

    try:
        return service.get_spill_visualization(
            spill_id=spill_id
        )

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
            detail="Failed to generate spill visualization.",
        ) from exc