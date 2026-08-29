import pytest
import numpy as np
from datetime import datetime, timezone

def test_drift_ensemble_equivalence(drift_engine, hindcast_service):
    engine, hindcast = drift_engine, hindcast_service
    
    obs_lat = 34.0
    obs_lon = 34.0
    obs_time = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    duration = 6.0
    
    ensemble_size = 100
    initial_radius_m = 500.0
    
    # 1. Generate start points manually so we can use the exact same ones for both
    rng = np.random.default_rng(42)
    angles = rng.uniform(0.0, 2.0 * np.pi, ensemble_size)
    radii = initial_radius_m * np.sqrt(rng.random(ensemble_size))
    east_m = radii * np.cos(angles)
    north_m = radii * np.sin(angles)

    start_lats, start_lons = hindcast._offset_position(
        latitude=obs_lat,
        longitude=obs_lon,
        east_m=east_m,
        north_m=north_m
    )
    
    # 2. Run sequential scalar loop
    scalar_ends = []
    scalar_state_counts = []
    
    for lat, lon in zip(start_lats, start_lons):
        traj = engine.backward_drift(
            obs_latitude=lat,
            obs_longitude=lon,
            obs_time=obs_time,
            duration_hours=duration,
        )
        if traj.states:
            scalar_ends.append((traj.end.latitude, traj.end.longitude))
        else:
            scalar_ends.append((np.nan, np.nan))
        scalar_state_counts.append(len(traj.states))

    # 3. Run vectorized ensemble
    vec_trajs = engine.backward_drift_ensemble(
        obs_latitudes=start_lats,
        obs_longitudes=start_lons,
        obs_time=obs_time,
        duration_hours=duration,
    )
    
    vec_ends = []
    vec_state_counts = []
    
    for traj in vec_trajs:
        if traj.states:
            vec_ends.append((traj.end.latitude, traj.end.longitude))
        else:
            vec_ends.append((np.nan, np.nan))
        vec_state_counts.append(len(traj.states))
        
    # 4. Compare
    assert len(scalar_ends) == len(vec_ends) == ensemble_size
    assert scalar_state_counts == vec_state_counts
    
    scalar_ends_arr = np.array(scalar_ends)
    vec_ends_arr = np.array(vec_ends)
    
    # Compare lat/lon
    mask = ~np.isnan(scalar_ends_arr[:, 0])
    
    np.testing.assert_array_equal(np.isnan(scalar_ends_arr[:, 0]), np.isnan(vec_ends_arr[:, 0]))
    
    np.testing.assert_allclose(
        scalar_ends_arr[mask], 
        vec_ends_arr[mask], 
        atol=1e-12
    )
