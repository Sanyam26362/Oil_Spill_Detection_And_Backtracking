from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ais_repository import AISRepository
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.scoring_engine import ScoringEngine
from app.services.weather_service import WeatherService


class AttributionEngine:
    """
    End-to-end vessel attribution orchestrator.

    Pipeline:

        SAR observation
            ↓
        backward hindcast
            ↓
        source estimate
            ↓
        PostGIS candidate extraction
            ↓
        AIS trajectory retrieval
            ↓
        behavioral scoring
            ↓
        ranked vessels

    Ground truth is never accessed here.
    """

    def __init__(
        self,
        weather_service: WeatherService,
        ais_repository: AISRepository | None = None,
        scoring_engine: ScoringEngine | None = None,
    ) -> None:

        self.drift_engine = DriftEngine(
            weather_service=weather_service,
            windage=0.03,
        )

        self.hindcast_service = HindcastService(
            drift_engine=self.drift_engine,
        )

        self.ais_repository = (
            ais_repository
            or AISRepository()
        )

        self.scoring_engine = (
            scoring_engine
            or ScoringEngine()
        )

    async def attribute(
        self,
        db: AsyncSession,
        observation_latitude: float,
        observation_longitude: float,
        observation_time: datetime,
        drift_duration_hours: float,
        ensemble_size: int = 100,
        initial_radius_m: float = 500.0,
        timestep_minutes: int = 15,
        candidate_radius_margin_km: float = 5.0,
        candidate_time_window_hours: float = 2.0,
        synthetic_only: bool | None = None,
        scenario_id: str | None = None,
    ) -> dict:
        """
        Perform end-to-end vessel attribution.
        """

        # ==========================================================
        # 0. ELIGIBILITY FILTER
        # ==========================================================

        # A2: Normalise naive observation_time to UTC so all downstream
        # comparisons against tz-aware datetimes do not raise TypeError.
        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(tzinfo=timezone.utc)

        estimated_release_time = (
            observation_time
            - timedelta(
                hours=drift_duration_hours
            )
        )
        
        search_end = (
            estimated_release_time
            + timedelta(
                hours=candidate_time_window_hours
            )
        )
        
        # We know synthetic AIS data begins strictly at 2019-01-01
        ais_start = datetime(2019, 1, 1, tzinfo=timezone.utc)
        if search_end < ais_start:
            return {
                "source_estimate": {
                    "latitude": observation_latitude,
                    "longitude": observation_longitude,
                    "radius_km": 0.0,
                },
                "estimated_release_time": (
                    estimated_release_time.isoformat()
                ),
                "candidate_count": 0,
                "candidates": [],
                "top_prediction": None,
            }

        # ==========================================================
        # 1. HINDCAST
        # ==========================================================

        # D3: Wrap blocking physics in threadpool so async event loop
        # is not blocked by NetCDF I/O and particle tracking.
        source_estimate = await run_in_threadpool(
            self.hindcast_service.backward_ensemble,
            obs_latitude=observation_latitude,
            obs_longitude=observation_longitude,
            obs_time=observation_time,
            duration_hours=drift_duration_hours,
            ensemble_size=ensemble_size,
            initial_radius_m=initial_radius_m,
            timestep_minutes=timestep_minutes,
            random_seed=42,
        )



        # ==========================================================
        # 2. CANDIDATE SEARCH
        # ==========================================================

        search_radius_km = max(
            source_estimate.radius_km
            + candidate_radius_margin_km,
            30.0,
        )

        search_start = (
            estimated_release_time
            - timedelta(
                hours=candidate_time_window_hours
            )
        )

        # B5: search_end was already computed above; redundant second
        # assignment removed here.

        candidate_ids = (
            await self.ais_repository
            .get_candidate_vessels(
                db=db,
                latitude=(
                    source_estimate
                    .centroid_latitude
                ),
                longitude=(
                    source_estimate
                    .centroid_longitude
                ),
                radius_km=search_radius_km,
                start_time=search_start,
                end_time=search_end,
                synthetic_only=synthetic_only,
                scenario_id=scenario_id,
            )
        )

        if not candidate_ids:
            return {
                "source_estimate": {
                    "latitude": (
                        source_estimate
                        .centroid_latitude
                    ),
                    "longitude": (
                        source_estimate
                        .centroid_longitude
                    ),
                    "radius_km": (
                        source_estimate.radius_km
                    ),
                },
                "estimated_release_time": (
                    estimated_release_time.isoformat()
                ),
                "candidate_count": 0,
                "candidates": [],
                "top_prediction": None,
            }

        # ==========================================================
        # 3. RETRIEVE CANDIDATE TRAJECTORIES
        # ==========================================================

        # B4: Use candidate_time_window_hours instead of hardcoded 2 so
        # the trajectory window stays in sync with the search window.
        trajectory_start = (
            estimated_release_time
            - timedelta(hours=candidate_time_window_hours)
        )

        trajectory_end = (
            estimated_release_time
            + timedelta(hours=candidate_time_window_hours)
        )

        positions = (
            await self.ais_repository
            .get_positions_for_vessels(
                db=db,
                vessel_ids=candidate_ids,
                start_time=trajectory_start,
                end_time=trajectory_end,
                synthetic_only=synthetic_only,
                scenario_id=scenario_id,
            )
        )

        # ==========================================================
        # 4. ORM → DATAFRAME
        # ==========================================================

        rows = []

        for position in positions:
            rows.append(
                {
                    "vessel_id": position.vessel_id,
                    "timestamp": position.timestamp,
                    "latitude": position.latitude,
                    "longitude": position.longitude,
                    "speed": position.speed,
                    "course": position.course,
                    "heading": position.heading,
                }
            )

        trajectory_df = pd.DataFrame(rows)

        if trajectory_df.empty:
            return {
                "source_estimate": {
                    "latitude": (
                        source_estimate
                        .centroid_latitude
                    ),
                    "longitude": (
                        source_estimate
                        .centroid_longitude
                    ),
                    "radius_km": (
                        source_estimate.radius_km
                    ),
                },
                "estimated_release_time": (
                    estimated_release_time.isoformat()
                ),
                "candidate_count": len(candidate_ids),
                "candidates": [],
                "top_prediction": None,
            }

        trajectory_df["timestamp"] = (
            pd.to_datetime(
                trajectory_df["timestamp"],
                utc=True,
            )
        )

        # The scoring engine currently expects a naive
        # UTC timestamp.
        trajectory_df["timestamp"] = (
            trajectory_df["timestamp"]
            .dt.tz_localize(None)
        )

        # A3: Convert to UTC first so non-UTC-aware inputs don't produce
        # a skewed naive timestamp. For UTC inputs the result is identical.
        _release_ts = pd.Timestamp(estimated_release_time)
        estimated_release_time_naive = (
            _release_ts.tz_convert("UTC").tz_localize(None)
            if _release_ts.tzinfo is not None
            else _release_ts.tz_localize(None)
        )

        # ==========================================================
        # 5. BEHAVIORAL SCORING
        # ==========================================================

        # E2: Build a vessel_id → sub-DataFrame mapping once so that
        # score_vessel does not re-scan the full DataFrame for every candidate.
        vessel_groups: dict[str, pd.DataFrame] = {
            vid: grp
            for vid, grp in trajectory_df.groupby("vessel_id", sort=False)
        }

        results = []

        for vessel_id in candidate_ids:

            score = (
                self.scoring_engine
                .score_vessel(
                    vessel_id=vessel_id,
                    df=trajectory_df,
                    source_latitude=(
                        source_estimate
                        .centroid_latitude
                    ),
                    source_longitude=(
                        source_estimate
                        .centroid_longitude
                    ),
                    estimated_release_time=(
                        estimated_release_time_naive
                    ),
                    vessel_df=vessel_groups.get(vessel_id),
                )
            )

            results.append(
                {
                    "vessel_id": score.vessel_id,
                    "score": score.total_score,
                    "proximity_score": (
                        score.proximity_score
                    ),
                    "temporal_score": (
                        score.temporal_score
                    ),
                    "slowdown_score": (
                        score.slowdown_score
                    ),
                    "loiter_score": (
                        score.loiter_score
                    ),
                    "approach_score": (
                        score.approach_score
                    ),
                    "departure_score": (
                        score.departure_score
                    ),
                    "closest_distance_km": (
                        score.closest_distance_km
                    ),
                    "minimum_event_speed_knots": (
                        score.minimum_event_speed_knots
                    ),
                }
            )

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        # ==========================================================
        # 6. RESPONSE
        # ==========================================================

        return {
            "source_estimate": {
                "latitude": (
                    source_estimate
                    .centroid_latitude
                ),
                "longitude": (
                    source_estimate
                    .centroid_longitude
                ),
                "radius_km": (
                    source_estimate.radius_km
                ),
            },
            "estimated_release_time": (
                estimated_release_time.isoformat()
            ),
            "candidate_count": len(
                candidate_ids
            ),
            "candidates": results,
            "top_prediction": (
                results[0]["vessel_id"]
                if results
                else None
            ),
        }