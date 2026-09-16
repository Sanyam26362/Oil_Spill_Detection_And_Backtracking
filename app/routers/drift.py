from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.weather_service import WeatherService
from app.models.schemas import (
    SpillPredictionResponse,
    PredictedPosition,
    PredictionTrajectoryPoint,
)


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
# Helper to Resolve Spill Info (Coordinates & Detected Timestamp)
# ----------------------------------------------------------------------
def _resolve_spill_info(spill_id: str) -> tuple[float, float, datetime]:
    """
    Search catalog service, database, or local JSON files to retrieve
    the observation coordinates and detection time for a given spill_id.
    """
    # 1. Try SpillCatalogService
    try:
        from app.services.spill_catalog_service import SpillCatalogService
        catalog = SpillCatalogService()
        for method_name in ("get_spill", "get_spill_by_id", "get_spill_detail", "get"):
            if hasattr(catalog, method_name):
                try:
                    spill = getattr(catalog, method_name)(spill_id)
                    if spill:
                        lat = getattr(spill, "observation_latitude", None) or getattr(spill, "latitude", None)
                        lon = getattr(spill, "observation_longitude", None) or getattr(spill, "longitude", None)
                        if lat is None and hasattr(spill, "centroid"):
                            lat = getattr(spill.centroid, "lat", None)
                            lon = getattr(spill.centroid, "lon", None)
                        dt = getattr(spill, "detected_at", None)
                        if lat is not None and lon is not None and dt is not None:
                            return float(lat), float(lon), dt
                except Exception:
                    pass
    except Exception:
        pass

    # 2. Try VisualizationService
    try:
        from app.services.visualization_service import VisualizationService
        vis = VisualizationService()
        for method_name in ("get_spill_visualization", "get_spill", "get_visualization_data"):
            if hasattr(vis, method_name):
                try:
                    data = getattr(vis, method_name)(spill_id)
                    if data and isinstance(data, dict) and "spill" in data:
                        sp = data["spill"]
                        lat = sp.get("latitude")
                        lon = sp.get("longitude")
                        dt = sp.get("detected_at")
                        if lat is not None and lon is not None and dt is not None:
                            if isinstance(dt, str):
                                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                            return float(lat), float(lon), dt
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Fallback: Scan local project JSON files in data and json_output
    for search_dir in [PROJECT_ROOT / "data", PROJECT_ROOT / "json_output"]:
        if not search_dir.exists():
            continue
        for json_file in search_dir.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                items = []
                if isinstance(content, dict):
                    if content.get("spill_id") == spill_id:
                        items = [content]
                    elif "items" in content and isinstance(content["items"], list):
                        items = content["items"]
                elif isinstance(content, list):
                    items = content

                for item in items:
                    if isinstance(item, dict) and item.get("spill_id") == spill_id:
                        lat = (
                            item.get("observation_latitude")
                            or item.get("latitude")
                            or (item.get("centroid") or {}).get("lat")
                        )
                        lon = (
                            item.get("observation_longitude")
                            or item.get("longitude")
                            or (item.get("centroid") or {}).get("lon")
                        )
                        dt = item.get("detected_at")
                        if lat is not None and lon is not None and dt is not None:
                            if isinstance(dt, str):
                                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                            return float(lat), float(lon), dt
            except Exception:
                continue

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Spill with ID '{spill_id}' could not be found.",
    )


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


@router.get(
    "/predict/{spill_id}",
    response_model=SpillPredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict future oil spill location and trajectory using spill_id",
)
@router.get(
    "/{spill_id}/predict",
    response_model=SpillPredictionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def predict_spill_drift_by_id(
    spill_id: str,
    hours: float = Query(6.0, gt=0, le=72.0, description="Hours to predict forward"),
    timestep_minutes: int = Query(15, ge=1, le=120, description="Waypoint interval in minutes"),
    drift_engine: DriftEngine = Depends(get_drift_engine),
):
    """
    Looks up the spill observation coordinates and detection time by spill_id,
    simulates forward drift over the specified hours (default 6h) using the
    active ERA5 and CMEMS yearly weather files, and outputs the predicted
    final position, net displacement, heading, and step-by-step trajectory.
    """
    start_lat, start_lon, start_time = _resolve_spill_info(spill_id)

    # Normalize timezone for netCDF weather lookups
    if start_time.tzinfo is not None:
        start_time_naive = start_time.replace(tzinfo=None)
    else:
        start_time_naive = start_time

    try:
        trajectory_result = drift_engine.forward_drift(
            start_latitude=start_lat,
            start_longitude=start_lon,
            start_time=start_time_naive,
            duration_hours=hours,
            timestep_minutes=timestep_minutes,
        )

        states = trajectory_result.states
        if not states:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Metocean velocity unavailable for spill '{spill_id}' at time {start_time}.",
            )

        trajectory_points: list[PredictionTrajectoryPoint] = []
        speed_records_knots: list[float] = []

        for state in states:
            u = state.drift_u
            v = state.drift_v
            speed_mps = float(math.hypot(u, v))
            speed_knots = float(speed_mps * 1.94384)
            speed_records_knots.append(speed_knots)

            heading_deg = float((math.degrees(math.atan2(u, v)) + 360.0) % 360.0)
            dist_km = float(drift_engine.haversine_km(start_lat, start_lon, state.latitude, state.longitude))

            trajectory_points.append(
                PredictionTrajectoryPoint(
                    timestamp=state.timestamp,
                    latitude=round(float(state.latitude), 6),
                    longitude=round(float(state.longitude), 6),
                    drift_speed_knots=round(speed_knots, 2),
                    drift_heading_deg=round(heading_deg, 1),
                    distance_from_start_km=round(dist_km, 3),
                )
            )

        final_state = states[-1]
        final_lat = float(final_state.latitude)
        final_lon = float(final_state.longitude)

        total_disp = float(drift_engine.haversine_km(start_lat, start_lon, final_lat, final_lon))

        # Net bearing from start to predicted position
        d_lon = math.radians(final_lon - start_lon)
        lat1_rad = math.radians(start_lat)
        lat2_rad = math.radians(final_lat)
        y = math.sin(d_lon) * math.cos(lat2_rad)
        x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
        net_bearing = float((math.degrees(math.atan2(y, x)) + 360.0) % 360.0)

        avg_speed = float(np.mean(speed_records_knots)) if speed_records_knots else 0.0

        return SpillPredictionResponse(
            spill_id=spill_id,
            forecast_hours=hours,
            initial_position=PredictedPosition(
                latitude=round(start_lat, 6),
                longitude=round(start_lon, 6),
                timestamp=start_time,
            ),
            predicted_position=PredictedPosition(
                latitude=round(final_lat, 6),
                longitude=round(final_lon, 6),
                timestamp=final_state.timestamp,
            ),
            total_displacement_km=round(total_disp, 3),
            net_heading_deg=round(net_bearing, 1),
            average_speed_knots=round(avg_speed, 2),
            trajectory=trajectory_points,
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drift forecast calculation failed: {str(exc)}",
        ) from exc