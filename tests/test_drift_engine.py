"""Tests for DriftEngine."""
import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from app.services.drift_engine import DriftEngine
from tests.conftest import CANONICAL_LAT, CANONICAL_LON, CANONICAL_TIME


class TestMoveParticle:
    """Test static particle movement calculation."""

    def test_east_movement(self):
        """Positive u should move particle east (increase longitude)."""
        new_lat, new_lon = DriftEngine.move_particle(
            latitude=0.0, longitude=0.0,
            u=1.0, v=0.0, seconds=3600.0,
        )
        assert new_lat == pytest.approx(0.0, abs=1e-6)
        assert new_lon > 0.0

    def test_north_movement(self):
        """Positive v should move particle north (increase latitude)."""
        new_lat, new_lon = DriftEngine.move_particle(
            latitude=0.0, longitude=0.0,
            u=0.0, v=1.0, seconds=3600.0,
        )
        assert new_lat > 0.0
        assert new_lon == pytest.approx(0.0, abs=1e-6)

    def test_negative_seconds_reverses(self):
        """Negative seconds should reverse the movement."""
        lat1, lon1 = DriftEngine.move_particle(
            latitude=33.5, longitude=34.0,
            u=0.5, v=-0.3, seconds=900.0,
        )
        lat2, lon2 = DriftEngine.move_particle(
            latitude=lat1, longitude=lon1,
            u=0.5, v=-0.3, seconds=-900.0,
        )
        assert lat2 == pytest.approx(33.5, abs=1e-6)
        assert lon2 == pytest.approx(34.0, abs=1e-6)

    def test_zero_velocity_no_movement(self):
        """Zero velocity should produce no movement."""
        new_lat, new_lon = DriftEngine.move_particle(
            latitude=33.5, longitude=34.0,
            u=0.0, v=0.0, seconds=3600.0,
        )
        assert new_lat == 33.5
        assert new_lon == 34.0


class TestForwardDrift:
    """Test forward drift trajectory."""

    def test_canonical_forward_6h(self, drift_engine):
        """6-hour forward drift from canonical point should match known result."""
        traj = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
            timestep_minutes=15,
        )
        # 6h / 15min = 24 steps + 1 initial = 25 states
        assert len(traj.states) == 25
        # Known endpoint approximately (33.4809, 34.0396)
        assert traj.end.latitude == pytest.approx(33.4809, abs=0.01)
        assert traj.end.longitude == pytest.approx(34.0396, abs=0.01)

    def test_trajectory_timestamps_monotonic(self, drift_engine):
        """Timestamps should be strictly increasing in forward drift."""
        traj = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=2.0,
        )
        timestamps = [s.timestamp for s in traj.states]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1]

    def test_invalid_duration_raises(self, drift_engine):
        """Zero or negative duration should raise ValueError."""
        with pytest.raises(ValueError):
            drift_engine.forward_drift(
                start_latitude=CANONICAL_LAT,
                start_longitude=CANONICAL_LON,
                start_time=CANONICAL_TIME,
                duration_hours=0.0,
            )


class TestBackwardDrift:
    """Test backward drift trajectory."""

    def test_backward_timestamps_decrease(self, drift_engine):
        """Timestamps should decrease in backward drift."""
        traj = drift_engine.backward_drift(
            obs_latitude=CANONICAL_LAT,
            obs_longitude=CANONICAL_LON,
            obs_time=CANONICAL_TIME,
            duration_hours=2.0,
        )
        timestamps = [s.timestamp for s in traj.states]
        for i in range(1, len(timestamps)):
            assert timestamps[i] < timestamps[i - 1]


class TestForwardBackwardConsistency:
    """Test forward→backward recovery accuracy."""

    def test_recovery_error_under_1km(self, drift_engine):
        """Forward then backward should recover start within ~0.2 km."""
        # Forward
        fwd = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
            timestep_minutes=15,
        )
        # Backward from endpoint
        bwd = drift_engine.backward_drift(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            timestep_minutes=15,
        )
        error_km = DriftEngine.haversine_km(
            CANONICAL_LAT, CANONICAL_LON,
            bwd.end.latitude, bwd.end.longitude,
        )
        assert error_km < 1.0, f"Recovery error {error_km:.4f} km exceeds 1.0 km"


class TestHaversine:
    """Test haversine distance calculation."""

    def test_same_point_zero(self):
        assert DriftEngine.haversine_km(33.5, 34.0, 33.5, 34.0) == pytest.approx(0.0)

    def test_known_distance(self):
        # 1 degree latitude ≈ 111.2 km
        dist = DriftEngine.haversine_km(33.0, 34.0, 34.0, 34.0)
        assert dist == pytest.approx(111.2, abs=0.5)
