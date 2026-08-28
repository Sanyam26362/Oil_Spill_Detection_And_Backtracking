from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.hindcast_service import HindcastService


@dataclass
class VesselScore:
    vessel_id: str

    total_score: float

    proximity_score: float
    temporal_score: float
    slowdown_score: float
    loiter_score: float
    approach_score: float
    departure_score: float

    closest_distance_km: float
    minimum_event_speed_knots: float


class ScoringEngine:
    """
    Interpretable vessel-attribution baseline.

    This engine does not know or access ground truth.

    It evaluates:
        - proximity
        - temporal proximity
        - slowdown
        - loitering
        - approach
        - departure
    """

    def score_vessel(
        self,
        vessel_id: str,
        df: pd.DataFrame,
        source_latitude: float,
        source_longitude: float,
        estimated_release_time: pd.Timestamp,
    ) -> VesselScore:

        vessel = (
            df[df["vessel_id"] == vessel_id]
            .copy()
            .sort_values("timestamp")
        )

        if vessel.empty:
            return VesselScore(
                vessel_id=vessel_id,
                total_score=0.0,
                proximity_score=0.0,
                temporal_score=0.0,
                slowdown_score=0.0,
                loiter_score=0.0,
                approach_score=0.0,
                departure_score=0.0,
                closest_distance_km=999.0,
                minimum_event_speed_knots=999.0,
            )

        # ----------------------------------------------------------
        # Distance from estimated source
        # ----------------------------------------------------------

        vessel["distance_km"] = vessel.apply(
            lambda row: HindcastService.haversine_km(
                source_latitude,
                source_longitude,
                row["latitude"],
                row["longitude"],
            ),
            axis=1,
        )

        # ----------------------------------------------------------
        # Time difference from estimated release
        # ----------------------------------------------------------

        vessel["time_diff_min"] = (
            (
                vessel["timestamp"]
                - estimated_release_time
            )
            .abs()
            .dt.total_seconds()
            / 60.0
        )

        # ----------------------------------------------------------
        # Windows
        # ----------------------------------------------------------

        event = vessel[
            vessel["time_diff_min"] <= 30
        ].copy()

        pre_window = vessel[
            (
                vessel["timestamp"]
                >= estimated_release_time
                - pd.Timedelta(minutes=120)
            )
            &
            (
                vessel["timestamp"]
                < estimated_release_time
            )
        ].copy()

        post_window = vessel[
            (
                vessel["timestamp"]
                > estimated_release_time
            )
            &
            (
                vessel["timestamp"]
                <= estimated_release_time
                + pd.Timedelta(minutes=120)
            )
        ].copy()

        # A narrower window specifically for loitering around
        # the spill event.
        loiter_window = vessel[
            vessel["time_diff_min"] <= 60
        ].copy()

        # ----------------------------------------------------------
        # 1. PROXIMITY
        # ----------------------------------------------------------

        closest_distance = float(
            event["distance_km"].min()
            if not event.empty
            else vessel["distance_km"].min()
        )

        proximity_score = float(
            np.clip(
                1.0 - closest_distance / 5.0,
                0.0,
                1.0,
            )
        )

        # ----------------------------------------------------------
        # 2. TEMPORAL PROXIMITY
        # ----------------------------------------------------------

        closest_time = float(
            vessel["time_diff_min"].min()
        )

        temporal_score = float(
            np.clip(
                1.0 - closest_time / 120.0,
                0.0,
                1.0,
            )
        )

        # ----------------------------------------------------------
        # 3. SLOWDOWN
        # ----------------------------------------------------------

        if not pre_window.empty:
            baseline_speed = float(
                pre_window["speed"].median()
            )
        else:
            baseline_speed = float(
                vessel["speed"].median()
            )

        if not event.empty:
            event_speed = float(
                event["speed"].median()
            )
        else:
            event_speed = baseline_speed

        if baseline_speed <= 0.1:
            slowdown_score = 0.0
        else:
            slowdown_ratio = (
                baseline_speed - event_speed
            ) / baseline_speed

            slowdown_score = float(
                np.clip(
                    slowdown_ratio,
                    0.0,
                    1.0,
                )
            )

        minimum_event_speed = float(
            event["speed"].min()
            if not event.empty
            else vessel["speed"].min()
        )

        # ----------------------------------------------------------
        # 4. LOITER
        # ----------------------------------------------------------

        near_source = loiter_window[
            loiter_window["distance_km"] <= 3.0
        ].copy()

        if len(near_source) >= 2:

            times = (
                near_source["timestamp"]
                .sort_values()
            )

            loiter_duration_minutes = (
                (
                    times.iloc[-1]
                    - times.iloc[0]
                )
                .total_seconds()
                / 60.0
            )

            loiter_score = float(
                np.clip(
                    loiter_duration_minutes / 30.0,
                    0.0,
                    1.0,
                )
            )

        else:
            loiter_score = 0.0

        # ----------------------------------------------------------
        # 5. APPROACH
        # ----------------------------------------------------------

        if len(pre_window) >= 2:

            distances = (
                pre_window["distance_km"]
                .to_numpy()
            )

            decreasing_steps = (
                np.diff(distances) < 0
            )

            approach_score = float(
                np.mean(decreasing_steps)
            )

        else:
            approach_score = 0.0

        # ----------------------------------------------------------
        # 6. DEPARTURE
        # ----------------------------------------------------------

        if len(post_window) >= 2:

            distances = (
                post_window["distance_km"]
                .to_numpy()
            )

            increasing_steps = (
                np.diff(distances) > 0
            )

            departure_score = float(
                np.mean(increasing_steps)
            )

        else:
            departure_score = 0.0

        # ----------------------------------------------------------
        # FINAL SCORE
        # ----------------------------------------------------------

        total_score = (
            0.25 * proximity_score
            + 0.15 * temporal_score
            + 0.20 * slowdown_score
            + 0.15 * loiter_score
            + 0.125 * approach_score
            + 0.125 * departure_score
        )

        return VesselScore(
            vessel_id=vessel_id,
            total_score=round(
                float(total_score),
                4,
            ),
            proximity_score=round(
                proximity_score,
                4,
            ),
            temporal_score=round(
                temporal_score,
                4,
            ),
            slowdown_score=round(
                slowdown_score,
                4,
            ),
            loiter_score=round(
                loiter_score,
                4,
            ),
            approach_score=round(
                approach_score,
                4,
            ),
            departure_score=round(
                departure_score,
                4,
            ),
            closest_distance_km=round(
                closest_distance,
                4,
            ),
            minimum_event_speed_knots=round(
                minimum_event_speed,
                4,
            ),
        )