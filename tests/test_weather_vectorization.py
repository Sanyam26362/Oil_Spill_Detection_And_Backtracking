import pytest
from datetime import datetime, timezone
import numpy as np

def test_weather_vectorization_equivalence(weather_service):
    """
    Test that the vectorized get_velocities method produces numerically equivalent 
    results to the scalar get_velocity method.
    """
    # Sample points covering ocean, near boundaries, and potentially land/NaN
    latitudes = np.linspace(33.0, 36.0, 50)
    longitudes = np.linspace(32.0, 35.0, 50)
    timestamp = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Scalar approach
    scalar_wind_u = []
    scalar_wind_v = []
    scalar_curr_u = []
    scalar_curr_v = []
    
    for lat, lon in zip(latitudes, longitudes):
        vel = weather_service.get_velocity(lat, lon, timestamp)
        scalar_wind_u.append(vel.wind_u)
        scalar_wind_v.append(vel.wind_v)
        scalar_curr_u.append(vel.current_u)
        scalar_curr_v.append(vel.current_v)

    scalar_wind_u = np.array(scalar_wind_u)
    scalar_wind_v = np.array(scalar_wind_v)
    scalar_curr_u = np.array(scalar_curr_u)
    scalar_curr_v = np.array(scalar_curr_v)

    # 2. Vectorized approach
    vec_wind_u, vec_wind_v, vec_curr_u, vec_curr_v = weather_service.get_velocities(
        latitudes, longitudes, timestamp
    )

    # Mask NaNs so we can compare valid numbers
    mask = ~np.isnan(scalar_wind_u)

    # Assert identical NaN placements
    np.testing.assert_array_equal(np.isnan(scalar_wind_u), np.isnan(vec_wind_u))
    np.testing.assert_array_equal(np.isnan(scalar_wind_v), np.isnan(vec_wind_v))
    np.testing.assert_array_equal(np.isnan(scalar_curr_u), np.isnan(vec_curr_u))
    np.testing.assert_array_equal(np.isnan(scalar_curr_v), np.isnan(vec_curr_v))

    # Assert numerical equivalence with a tight tolerance
    tolerance = 1e-12

    np.testing.assert_allclose(vec_wind_u[mask], scalar_wind_u[mask], atol=tolerance)
    np.testing.assert_allclose(vec_wind_v[mask], scalar_wind_v[mask], atol=tolerance)
    np.testing.assert_allclose(vec_curr_u[mask], scalar_curr_u[mask], atol=tolerance)
    np.testing.assert_allclose(vec_curr_v[mask], scalar_curr_v[mask], atol=tolerance)

    # Print explicit max diffs for the report if needed
    max_diff_u = np.max(np.abs(vec_wind_u[mask] - scalar_wind_u[mask]))
    max_diff_v = np.max(np.abs(vec_wind_v[mask] - scalar_wind_v[mask]))
    print(f"Max diff wind_u: {max_diff_u}")
    print(f"Max diff wind_v: {max_diff_v}")
