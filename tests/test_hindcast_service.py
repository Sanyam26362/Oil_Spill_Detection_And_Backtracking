"""Tests for HindcastService."""
import pytest
from datetime import datetime, timezone

from app.services.drift_engine import DriftEngine
from tests.conftest import CANONICAL_LAT, CANONICAL_LON, CANONICAL_TIME


class TestBackwardEnsemble:
    """Test backward particle ensemble."""

    def test_ensemble_produces_particles(self, hindcast_service, drift_engine):
        """Ensemble should produce the requested number of particles."""
        # First do a forward drift to get an observation point
        fwd = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
        )
        estimate = hindcast_service.backward_ensemble(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            ensemble_size=50,
            random_seed=42,
        )
        assert len(estimate.particles) == 50

    def test_ensemble_centroid_near_source(self, hindcast_service, drift_engine):
        """Ensemble centroid should recover near the true source."""
        fwd = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
        )
        estimate = hindcast_service.backward_ensemble(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            ensemble_size=100,
            random_seed=42,
        )
        error_km = DriftEngine.haversine_km(
            CANONICAL_LAT, CANONICAL_LON,
            estimate.centroid_latitude, estimate.centroid_longitude,
        )
        # Should be approximately 0.16-0.20 km
        assert error_km < 1.0, f"Centroid error {error_km:.4f} km"

    def test_ensemble_reproducible(self, hindcast_service, drift_engine):
        """Same seed should produce identical results."""
        fwd = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
        )
        e1 = hindcast_service.backward_ensemble(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            ensemble_size=20,
            random_seed=42,
        )
        e2 = hindcast_service.backward_ensemble(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            ensemble_size=20,
            random_seed=42,
        )
        assert e1.centroid_latitude == e2.centroid_latitude
        assert e1.centroid_longitude == e2.centroid_longitude

    def test_invalid_ensemble_size_raises(self, hindcast_service):
        """Zero ensemble size should raise ValueError."""
        with pytest.raises(ValueError):
            hindcast_service.backward_ensemble(
                obs_latitude=CANONICAL_LAT,
                obs_longitude=CANONICAL_LON,
                obs_time=CANONICAL_TIME,
                duration_hours=6.0,
                ensemble_size=0,
            )


class TestDensityGrid:
    """Test density grid generation."""

    def test_density_grid_shape(self, hindcast_service, drift_engine):
        """Density grid should have correct shape."""
        fwd = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
        )
        estimate = hindcast_service.backward_ensemble(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            ensemble_size=50,
            random_seed=42,
        )
        density = hindcast_service.build_density_grid(
            source_estimate=estimate,
            grid_size=20,
        )
        assert density.density.shape == (20, 20)
        assert len(density.latitudes) == 20
        assert len(density.longitudes) == 20

    def test_density_sums_to_one(self, hindcast_service, drift_engine):
        """Normalized density should sum to approximately 1.0."""
        fwd = drift_engine.forward_drift(
            start_latitude=CANONICAL_LAT,
            start_longitude=CANONICAL_LON,
            start_time=CANONICAL_TIME,
            duration_hours=6.0,
        )
        estimate = hindcast_service.backward_ensemble(
            obs_latitude=fwd.end.latitude,
            obs_longitude=fwd.end.longitude,
            obs_time=fwd.end.timestamp,
            duration_hours=6.0,
            ensemble_size=50,
            random_seed=42,
        )
        density = hindcast_service.build_density_grid(
            source_estimate=estimate,
            grid_size=20,
        )
        assert density.density.sum() == pytest.approx(1.0, abs=0.01)
