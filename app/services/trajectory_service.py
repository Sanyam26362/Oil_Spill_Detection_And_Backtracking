"""
TrajectoryService: Extracts behavioral features from AIS positions.

Responsibilities:
    - Distance from source calculation
    - Speed change detection
    - Approach/departure rate computation

Repository = database access.
TrajectoryService = trajectory/feature extraction.
ScoringEngine = score features.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.drift_engine import DriftEngine


@dataclass
class VesselBehaviorFeatures:
    """Behavioral features extracted from AIS trajectory."""

    vessel_id: str
    record_count: int

    # Spatial
    min_distance_km: float
    mean_distance_km: float

    # Temporal
    min_time_diff_minutes: float

    # Speed behavior
    approach_speed_knots: float
    event_speed_knots: float
    departure_speed_knots: float
    slowdown_ratio: float

    # Approach/departure
    approach_fraction: float  # fraction of pre-event steps decreasing distance
    departure_fraction: float  # fraction of post-event steps increasing distance

    # Loiter
    loiter_duration_minutes: float
    loiter_record_count: int


class TrajectoryService:
    """
    Extract behavioral features from raw AIS positions.
    
    This service does NOT access ground truth.
    It takes AIS positions and a reference source estimate.
    """

    @staticmethod
    def extract_features(
        vessel_id: str,
        df: pd.DataFrame,
        source_latitude: float,
        source_longitude: float,
        estimated_release_time: pd.Timestamp,
        near_source_km: float = 3.0,
        loiter_window_minutes: float = 60.0,
        pre_window_minutes: float = 120.0,
        post_window_minutes: float = 120.0,
    ) -> VesselBehaviorFeatures:
        """Extract behavioral features for one vessel."""

        vessel = (
            df[df["vessel_id"] == vessel_id]
            .copy()
            .sort_values("timestamp")
        )

        if vessel.empty:
            return VesselBehaviorFeatures(
                vessel_id=vessel_id,
                record_count=0,
                min_distance_km=999.0,
                mean_distance_km=999.0,
                min_time_diff_minutes=9999.0,
                approach_speed_knots=0.0,
                event_speed_knots=0.0,
                departure_speed_knots=0.0,
                slowdown_ratio=0.0,
                approach_fraction=0.0,
                departure_fraction=0.0,
                loiter_duration_minutes=0.0,
                loiter_record_count=0,
            )

        # Compute distances
        vessel["distance_km"] = vessel.apply(
            lambda row: DriftEngine.haversine_km(
                source_latitude, source_longitude,
                row["latitude"], row["longitude"],
            ),
            axis=1,
        )

        # Time differences
        vessel["time_diff_min"] = (
            (vessel["timestamp"] - estimated_release_time)
            .abs()
            .dt.total_seconds()
            / 60.0
        )

        # Windows
        pre = vessel[
            (vessel["timestamp"] >= estimated_release_time - pd.Timedelta(minutes=pre_window_minutes))
            & (vessel["timestamp"] < estimated_release_time)
        ]
        post = vessel[
            (vessel["timestamp"] > estimated_release_time)
            & (vessel["timestamp"] <= estimated_release_time + pd.Timedelta(minutes=post_window_minutes))
        ]
        event = vessel[vessel["time_diff_min"] <= 30]
        loiter_window = vessel[vessel["time_diff_min"] <= loiter_window_minutes]

        # Speed features
        approach_speed = float(pre["speed"].median()) if not pre.empty else 0.0
        event_speed = float(event["speed"].median()) if not event.empty else approach_speed
        departure_speed = float(post["speed"].median()) if not post.empty else 0.0

        if approach_speed > 0.1:
            slowdown_ratio = max(0.0, (approach_speed - event_speed) / approach_speed)
        else:
            slowdown_ratio = 0.0

        # Approach fraction
        if len(pre) >= 2:
            distances = pre["distance_km"].to_numpy()
            approach_fraction = float(np.mean(np.diff(distances) < 0))
        else:
            approach_fraction = 0.0

        # Departure fraction
        if len(post) >= 2:
            distances = post["distance_km"].to_numpy()
            departure_fraction = float(np.mean(np.diff(distances) > 0))
        else:
            departure_fraction = 0.0

        # Loiter
        near_source = loiter_window[loiter_window["distance_km"] <= near_source_km]
        if len(near_source) >= 2:
            times = near_source["timestamp"].sort_values()
            loiter_duration = (times.iloc[-1] - times.iloc[0]).total_seconds() / 60.0
        else:
            loiter_duration = 0.0

        return VesselBehaviorFeatures(
            vessel_id=vessel_id,
            record_count=len(vessel),
            min_distance_km=float(vessel["distance_km"].min()),
            mean_distance_km=float(vessel["distance_km"].mean()),
            min_time_diff_minutes=float(vessel["time_diff_min"].min()),
            approach_speed_knots=round(approach_speed, 2),
            event_speed_knots=round(event_speed, 2),
            departure_speed_knots=round(departure_speed, 2),
            slowdown_ratio=round(slowdown_ratio, 4),
            approach_fraction=round(approach_fraction, 4),
            departure_fraction=round(departure_fraction, 4),
            loiter_duration_minutes=round(loiter_duration, 2),
            loiter_record_count=len(near_source),
        )
