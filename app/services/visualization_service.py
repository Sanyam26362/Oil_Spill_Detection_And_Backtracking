from __future__ import annotations

from datetime import datetime, timezone
from math import atan2, degrees, hypot

from app.models.drift import EnvironmentalVelocity
from app.schemas.visualization import (
    CurrentVisualization,
    EnvironmentVisualization,
    SourceEstimateVisualization,
    SpillVisualization,
    TrajectoryPoint,
    VisualizationResponse,
    WindVisualization,
)
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.spill_catalog_service import SpillCatalogService


class VisualizationService:
    """
    Orchestrates the existing spill, hindcast, drift and
    environmental services for frontend visualization.

    IMPORTANT:
    This service does NOT implement a new drift model.
    It only calls the existing services and converts their
    results into a frontend-friendly response.
    """

    def __init__(
        self,
        drift_engine: DriftEngine,
        hindcast_service: HindcastService,
    ) -> None:
        self.drift_engine = drift_engine
        self.hindcast_service = hindcast_service

    @staticmethod
    def _ensure_utc(timestamp: datetime) -> datetime:
        """
        Ensure timestamps returned by the API are timezone-aware UTC.
        """

        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _wind_direction(
        u: float,
        v: float,
    ) -> float:
        """
        Meteorological wind direction.

        Returns the direction the wind is COMING FROM.

        0   = North
        90  = East
        180 = South
        270 = West
        """

        direction = (
            degrees(
                atan2(-u, -v)
            )
            + 360.0
        ) % 360.0

        return round(direction, 2)

    @staticmethod
    def _current_direction(
        u: float,
        v: float,
    ) -> float:
        """
        Ocean-current direction.

        Returns the direction the current is MOVING TOWARD.

        0   = North
        90  = East
        180 = South
        270 = West
        """

        direction = (
            degrees(
                atan2(u, v)
            )
            + 360.0
        ) % 360.0

        return round(direction, 2)

    @classmethod
    def _build_environment(
        cls,
        environment: EnvironmentalVelocity,
    ) -> EnvironmentVisualization:
        """
        Convert raw environmental velocity components into
        frontend-friendly wind/current objects.
        """

        wind_u = float(environment.wind_u)
        wind_v = float(environment.wind_v)

        current_u = float(environment.current_u)
        current_v = float(environment.current_v)

        wind_speed = hypot(
            wind_u,
            wind_v,
        )

        current_speed = hypot(
            current_u,
            current_v,
        )

        return EnvironmentVisualization(
            wind=WindVisualization(
                u=round(wind_u, 6),
                v=round(wind_v, 6),
                speed=round(wind_speed, 6),
                direction=cls._wind_direction(
                    wind_u,
                    wind_v,
                ),
            ),
            current=CurrentVisualization(
                u=round(current_u, 6),
                v=round(current_v, 6),
                speed=round(current_speed, 6),
                direction=cls._current_direction(
                    current_u,
                    current_v,
                ),
            ),
        )

    @staticmethod
    def _build_trajectory(
        states,
    ) -> list[TrajectoryPoint]:
        """
        Convert existing DriftEngine ParticleState objects
        into the frontend response format.
        """

        return [
            TrajectoryPoint(
                timestamp=VisualizationService._ensure_utc(
                    state.timestamp
                ),
                latitude=round(
                    float(state.latitude),
                    6,
                ),
                longitude=round(
                    float(state.longitude),
                    6,
                ),
            )
            for state in states
        ]

    def get_spill_visualization(
        self,
        spill_id: str,
    ) -> VisualizationResponse:
        """
        Build all visualization information for one demo spill.

        Flow:

            SpillCatalogService
                    ↓
            detection location/time
                    ↓
            WeatherService
                    ↓
            environmental conditions

                    +

            HindcastService
                    ↓
            source estimate

                    +

            DriftEngine
                    ↓
            actual backward trajectory
        """

        spill = SpillCatalogService.get_spill(
            spill_id
        )

        if not spill:
            raise KeyError(
                f"Spill '{spill_id}' not found in demo catalog."
            )

        latitude = float(
            spill["observation_latitude"]
        )

        longitude = float(
            spill["observation_longitude"]
        )

        detected_at = datetime.fromisoformat(
            spill["detected_at"]
        )

        detected_at = self._ensure_utc(
            detected_at
        )

        duration_hours = float(
            spill["estimated_age_hours"]
        )

        timestep_minutes = 15

        # ----------------------------------------------------------
        # 1. Environmental conditions at spill detection
        # ----------------------------------------------------------

        environment = (
            self.drift_engine.weather_service.get_velocity(
                latitude=latitude,
                longitude=longitude,
                timestamp=detected_at,
            )
        )

        environment_response = self._build_environment(
            environment
        )

        # ----------------------------------------------------------
        # 2. Existing hindcast source estimate
        # ----------------------------------------------------------

        if (
            spill.get("estimated_source_latitude") is not None
            and spill.get("estimated_source_longitude") is not None
            and spill.get("estimated_source_radius_km") is not None
        ):
            source_latitude = float(spill["estimated_source_latitude"])
            source_longitude = float(spill["estimated_source_longitude"])
            source_radius_km = float(spill["estimated_source_radius_km"])
        else:
            source_estimate = (
                self.hindcast_service.backward_ensemble(
                    obs_latitude=latitude,
                    obs_longitude=longitude,
                    obs_time=detected_at,
                    duration_hours=duration_hours,
                    ensemble_size=100,
                    initial_radius_m=500.0,
                    timestep_minutes=timestep_minutes,
                    random_seed=42,
                )
            )
            source_latitude = float(source_estimate.centroid_latitude)
            source_longitude = float(source_estimate.centroid_longitude)
            source_radius_km = float(source_estimate.radius_km)

        # ----------------------------------------------------------
        # 3. Actual deterministic backward trajectory
        # ----------------------------------------------------------
        #
        # This is NOT a straight line.
        #
        # It uses the same existing DriftEngine and WeatherService
        # used by the rest of the system.
        #

        trajectory = self.drift_engine.backward_drift(
            obs_latitude=latitude,
            obs_longitude=longitude,
            obs_time=detected_at,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
        )

        if not trajectory.states:
            raise RuntimeError(
                "No valid trajectory could be generated for "
                f"spill '{spill_id}'."
            )

        trajectory_points = self._build_trajectory(
            trajectory.states
        )

        # ----------------------------------------------------------
        # 4. Build response
        # ----------------------------------------------------------

        return VisualizationResponse(
            spill=SpillVisualization(
                spill_id=spill_id,
                latitude=latitude,
                longitude=longitude,
                detected_at=detected_at,
            ),
            source_estimate=SourceEstimateVisualization(
                latitude=round(source_latitude, 6),
                longitude=round(source_longitude, 6),
                radius_km=round(source_radius_km, 4),
            ),
            environment=environment_response,
            trajectory=trajectory_points,
        )