import sys
from pathlib import Path
from datetime import datetime, timezone
import xarray as xr
import numpy as np

PROJECT_ROOT = Path("d:/projects/oil-spill-backend")
sys.path.append(str(PROJECT_ROOT))

from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService

def main():
    ws = WeatherService(
        era5_path=PROJECT_ROOT / "data" / "weather" / "raw" / "era5_wind_2019-07-event.nc",
        cmems_path=PROJECT_ROOT / "data" / "ocean" / "raw" / "med_currents_2019-07-event.nc",
    )
    engine = DriftEngine(ws)
    hindcast = HindcastService(engine)
    
    print("--- 1. Scalar vs Vectorized ---")
    latitudes = np.linspace(33.0, 36.0, 50)
    longitudes = np.linspace(32.0, 35.0, 50)
    timestamp = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    scalar_wind_u, scalar_wind_v = [], []
    scalar_curr_u, scalar_curr_v = [], []
    for lat, lon in zip(latitudes, longitudes):
        vel = ws.get_velocity(lat, lon, timestamp)
        scalar_wind_u.append(vel.wind_u)
        scalar_wind_v.append(vel.wind_v)
        scalar_curr_u.append(vel.current_u)
        scalar_curr_v.append(vel.current_v)
        
    vec_wind_u, vec_wind_v, vec_curr_u, vec_curr_v = ws.get_velocities(latitudes, longitudes, timestamp)
    
    mask = ~np.isnan(scalar_wind_u)
    mask_c = ~np.isnan(scalar_curr_u)
    print(f"max current_u diff: {np.max(np.abs(np.array(scalar_curr_u)[mask_c] - vec_curr_u[mask_c]))}")
    print(f"max current_v diff: {np.max(np.abs(np.array(scalar_curr_v)[mask_c] - vec_curr_v[mask_c]))}")
    print(f"max wind_u diff: {np.max(np.abs(np.array(scalar_wind_u)[mask] - vec_wind_u[mask]))}")
    print(f"max wind_v diff: {np.max(np.abs(np.array(scalar_wind_v)[mask] - vec_wind_v[mask]))}")
    
    print("\n--- 2. Trajectory Equivalence ---")
    obs_lat = 34.0
    obs_lon = 34.0
    duration = 6.0
    ensemble_size = 100
    
    rng = np.random.default_rng(42)
    angles = rng.uniform(0.0, 2.0 * np.pi, ensemble_size)
    radii = 500.0 * np.sqrt(rng.random(ensemble_size))
    east_m = radii * np.cos(angles)
    north_m = radii * np.sin(angles)
    
    start_lats, start_lons = hindcast._offset_position(obs_lat, obs_lon, east_m, north_m)
    
    scalar_lats, scalar_lons = [], []
    valid_scalar = 0
    for lat, lon in zip(start_lats, start_lons):
        traj = engine.backward_drift(lat, lon, timestamp, duration)
        if traj.states:
            scalar_lats.append(traj.end.latitude)
            scalar_lons.append(traj.end.longitude)
            valid_scalar += 1
        else:
            scalar_lats.append(np.nan)
            scalar_lons.append(np.nan)
            
    vec_trajs = engine.backward_drift_ensemble(start_lats, start_lons, timestamp, duration)
    vec_lats, vec_lons = [], []
    valid_vec = 0
    for traj in vec_trajs:
        if traj.states:
            vec_lats.append(traj.end.latitude)
            vec_lons.append(traj.end.longitude)
            valid_vec += 1
        else:
            vec_lats.append(np.nan)
            vec_lons.append(np.nan)
            
    mask2 = ~np.isnan(scalar_lats)
    print(f"valid particle count diff: {abs(valid_scalar - valid_vec)}")
    print(f"max latitude diff: {np.max(np.abs(np.array(scalar_lats)[mask2] - np.array(vec_lats)[mask2]))}")
    print(f"max longitude diff: {np.max(np.abs(np.array(scalar_lons)[mask2] - np.array(vec_lons)[mask2]))}")
    
    c_lat_s = np.mean(np.array(scalar_lats)[mask2])
    c_lon_s = np.mean(np.array(scalar_lons)[mask2])
    c_lat_v = np.mean(np.array(vec_lats)[mask2])
    c_lon_v = np.mean(np.array(vec_lons)[mask2])
    
    print(f"centroid latitude diff: {abs(c_lat_s - c_lat_v)}")
    print(f"centroid longitude diff: {abs(c_lon_s - c_lon_v)}")
    
    # Calculate radius difference
    from app.models.drift import ParticleSource
    
    scalar_particles = [ParticleSource(lat, lon, timestamp) for lat, lon in zip(np.array(scalar_lats)[mask2], np.array(scalar_lons)[mask2])]
    vec_particles = [ParticleSource(lat, lon, timestamp) for lat, lon in zip(np.array(vec_lats)[mask2], np.array(vec_lons)[mask2])]
    
    scalar_dist = [hindcast.haversine_km(c_lat_s, c_lon_s, p.latitude, p.longitude) for p in scalar_particles]
    vec_dist = [hindcast.haversine_km(c_lat_v, c_lon_v, p.latitude, p.longitude) for p in vec_particles]
    
    rad_s = float(np.max(scalar_dist))
    rad_v = float(np.max(vec_dist))
    
    print(f"radius diff: {abs(rad_s - rad_v)}")
    
    ws.close()

if __name__ == "__main__":
    main()
