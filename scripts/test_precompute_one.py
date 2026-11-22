import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.spill_catalog_service import SpillCatalogService
from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.visualization_service import VisualizationService
from app.services.demo_vessel_evidence_service import DemoVesselEvidenceService
from app.routers.demo_spills import _build_spill_vessels
from app.models.schemas import (
    DemoSpillDetail,
    CentroidSchema,
    DemoBacktrackResponse,
    SpillPredictionResponse,
    PredictedPosition,
    PredictionTrajectoryPoint,
)
import json
import math
import numpy as np

def run():
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    SpillCatalogService.initialize()
    s = SpillCatalogService.get_spill('spill_31e02e')
    print("Spill 31e02e:", s["spill_id"], s["ranked_top_vessel"])

    ws = WeatherService(
        weather_yearly_dir=PROJECT_ROOT / "data" / "weather" / "raw" / "yearly",
        ocean_yearly_dir=PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"
    )
    de = DriftEngine(weather_service=ws, windage=0.03)
    hs = HindcastService(drift_engine=de)
    vs = VisualizationService(drift_engine=de, hindcast_service=hs)

    # 1. Visualization
    viz = vs.get_spill_visualization('spill_31e02e')
    viz_dict = viz.model_dump(mode="json")
    print("Viz OK, points:", len(viz_dict["trajectory"]))

    # 2. Forward forecast
    dt = datetime.fromisoformat(s['detected_at'])
    if dt.tzinfo is not None:
        dt_naive = dt.replace(tzinfo=None)
    else:
        dt_naive = dt
    start_lat = float(s["observation_latitude"])
    start_lon = float(s["observation_longitude"])

    drift_traj = de.forward_drift(
        start_latitude=start_lat,
        start_longitude=start_lon,
        start_time=dt_naive,
        duration_hours=6.0,
        timestep_minutes=15
    )
    states = drift_traj.states
    trajectory_points = []
    speed_records_knots = []
    for state in states:
        u = state.drift_u
        v = state.drift_v
        spd_mps = float(math.hypot(u, v))
        spd_knots = float(spd_mps * 1.94384)
        speed_records_knots.append(spd_knots)
        heading_deg = float((math.degrees(math.atan2(u, v)) + 360.0) % 360.0)
        dist_km = float(DriftEngine.haversine_km(start_lat, start_lon, state.latitude, state.longitude))
        trajectory_points.append(
            PredictionTrajectoryPoint(
                timestamp=state.timestamp,
                latitude=round(float(state.latitude), 6),
                longitude=round(float(state.longitude), 6),
                drift_speed_knots=round(spd_knots, 2),
                drift_heading_deg=round(heading_deg, 1),
                distance_from_start_km=round(dist_km, 3),
            )
        )
    final_state = states[-1]
    final_lat = float(final_state.latitude)
    final_lon = float(final_state.longitude)
    total_disp = float(DriftEngine.haversine_km(start_lat, start_lon, final_lat, final_lon))
    d_lon = math.radians(final_lon - start_lon)
    lat1_rad = math.radians(start_lat)
    lat2_rad = math.radians(final_lat)
    y = math.sin(d_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
    net_bearing = float((math.degrees(math.atan2(y, x)) + 360.0) % 360.0)
    avg_speed = float(np.mean(speed_records_knots)) if speed_records_knots else 0.0

    forecast = SpillPredictionResponse(
        spill_id='spill_31e02e',
        forecast_hours=6.0,
        initial_position=PredictedPosition(
            latitude=round(start_lat, 6),
            longitude=round(start_lon, 6),
            timestamp=dt,
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
    forecast_dict = forecast.model_dump(mode="json")
    print("Forecast OK, points:", len(forecast_dict["trajectory"]))

    # 3. Backtrack response
    backtrack = DemoBacktrackResponse(
        spill_id='spill_31e02e',
        backtrack={
            "observation": {
                "latitude": s["observation_latitude"],
                "longitude": s["observation_longitude"],
                "timestamp": s["detected_at"],
            },
            "estimated_release_time": s.get("estimated_release_time"),
            "source_estimate": {
                "latitude": s.get("estimated_source_latitude"),
                "longitude": s.get("estimated_source_longitude"),
                "radius_km": s.get("estimated_source_radius_km"),
            },
        },
        attribution={
            "candidate_count": s.get("candidate_count", 0),
            "top_vessel": s.get("ranked_top_vessel"),
            "top_score": s.get("ranked_top_score"),
        }
    )
    backtrack_dict = backtrack.model_dump(mode="json")
    print("Backtrack OK:", backtrack_dict["attribution"])

    ws.close()

if __name__ == "__main__":
    run()
