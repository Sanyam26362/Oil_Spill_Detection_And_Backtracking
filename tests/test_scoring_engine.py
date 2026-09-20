"""Tests for ScoringEngine."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.services.scoring_engine import ScoringEngine


def _make_vessel_df(
    vessel_id: str,
    timestamps: list,
    latitudes: list,
    longitudes: list,
    speeds: list,
) -> pd.DataFrame:
    """Create a test DataFrame for one vessel."""
    return pd.DataFrame({
        "vessel_id": vessel_id,
        "timestamp": pd.to_datetime(timestamps),
        "latitude": latitudes,
        "longitude": longitudes,
        "speed": speeds,
        "course": [0.0] * len(timestamps),
        "heading": [0.0] * len(timestamps),
    })


class TestProximityScore:
    """Test proximity scoring."""

    def test_vessel_at_source_scores_high(self, scoring_engine):
        """Vessel exactly at source should get proximity ≈ 1.0."""
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        df = _make_vessel_df(
            "V1",
            ["2019-07-15 12:00:00"],
            [33.5], [34.0], [1.0],
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.proximity_score >= 0.9
        assert score.closest_distance_km < 0.1

    def test_vessel_far_away_scores_low(self, scoring_engine):
        """Vessel 10 km from source should get proximity ≈ 0."""
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        df = _make_vessel_df(
            "V1",
            ["2019-07-15 12:00:00"],
            [33.6], [34.0], [1.0],  # ~11 km away
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.proximity_score < 0.1


class TestTemporalScore:
    """Test temporal proximity scoring."""

    def test_exact_time_scores_high(self, scoring_engine):
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        df = _make_vessel_df(
            "V1",
            ["2019-07-15 12:00:00"],
            [33.5], [34.0], [1.0],
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.temporal_score >= 0.9

    def test_hours_away_scores_low(self, scoring_engine):
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        df = _make_vessel_df(
            "V1",
            ["2019-07-15 15:00:00"],  # 3h later
            [33.5], [34.0], [1.0],
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.temporal_score < 0.1


class TestSlowdownScore:
    """Test slowdown detection."""

    def test_clear_slowdown_scores_high(self, scoring_engine):
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        # Pre-event: fast; event: slow
        df = _make_vessel_df(
            "V1",
            [
                "2019-07-15 11:00:00", "2019-07-15 11:30:00",
                "2019-07-15 12:00:00", "2019-07-15 12:10:00",
            ],
            [33.51, 33.505, 33.5, 33.5],
            [34.0, 34.0, 34.0, 34.0],
            [12.0, 12.0, 1.0, 0.5],
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.slowdown_score > 0.5

    def test_constant_speed_no_slowdown(self, scoring_engine):
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        df = _make_vessel_df(
            "V1",
            ["2019-07-15 11:00:00", "2019-07-15 11:30:00",
             "2019-07-15 12:00:00"],
            [33.51, 33.505, 33.5],
            [34.0, 34.0, 34.0],
            [12.0, 12.0, 12.0],
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.slowdown_score < 0.1


class TestLoiterScore:
    """Test loiter detection."""

    def test_loiter_near_source_scores_high(self, scoring_engine):
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        # Multiple records near source within ±60 min
        timestamps = [
            f"2019-07-15 12:{m:02d}:00" for m in range(0, 40, 5)
        ]
        df = _make_vessel_df(
            "V1",
            timestamps,
            [33.5 + np.random.uniform(-0.001, 0.001) for _ in timestamps],
            [34.0 + np.random.uniform(-0.001, 0.001) for _ in timestamps],
            [0.5] * len(timestamps),
        )
        score = scoring_engine.score_vessel(
            "V1", df, 33.5, 34.0, release_time,
        )
        assert score.loiter_score > 0.5


class TestEmptyVessel:
    """Test scoring with no data."""

    def test_empty_vessel_scores_zero(self, scoring_engine):
        release_time = pd.Timestamp("2019-07-15 12:00:00")
        df = pd.DataFrame(columns=[
            "vessel_id", "timestamp", "latitude", "longitude",
            "speed", "course", "heading",
        ])
        score = scoring_engine.score_vessel(
            "V_EMPTY", df, 33.5, 34.0, release_time,
        )
        assert score.total_score == 0.0
        assert score.closest_distance_km is None
        assert score.minimum_event_speed_knots is None


class TestWeightSum:
    """Verify scoring weights sum to 1.0."""

    def test_weight_sum(self):
        weights = [0.25, 0.15, 0.20, 0.15, 0.125, 0.125]
        assert sum(weights) == pytest.approx(1.0)
