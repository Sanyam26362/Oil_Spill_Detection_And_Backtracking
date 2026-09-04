from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import cos, radians
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ais_repository import AISRepository
from app.services.drift_engine import DriftEngine


class DemoVesselEvidenceService:
    """
    Builds frontend-ready attribution evidence.

    The vessel list is supplied by the existing /vessels endpoint.
    Therefore this service NEVER performs a second attribution/ranking.

    Real vessel:
        - trajectory comes from PostgreSQL AIS

    Mock vessels:
        - deterministic visualization trajectories only
    """

    TRAJECTORY_HALF_WINDOW_HOURS = 2
    DISPLAY_TRAJECTORY_POINTS = 5

    def __init__(self):
        self.ais_repository = AISRepository()

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @staticmethod
    def _position_to_dict(position: Any) -> dict:
        return {
            "timestamp": DemoVesselEvidenceService._ensure_utc(
                position.timestamp
            ),
            "latitude": float(position.latitude),
            "longitude": float(position.longitude),
            "speed": (
                float(position.speed)
                if position.speed is not None
                else None
            ),
            "course": (
                float(position.course)
                if position.course is not None
                else None
            ),
            "heading": (
                float(position.heading)
                if position.heading is not None
                else None
            ),
        }

    @staticmethod
    def _offset_point(
        latitude: float,
        longitude: float,
        north_km: float,
        east_km: float,
    ) -> tuple[float, float]:
        """
        Approximate a small north/east offset in kilometres.
        """

        latitude_delta = north_km / 111.32

        longitude_delta = east_km / (
            111.32 * max(cos(radians(latitude)), 0.2)
        )

        return (
            latitude + latitude_delta,
            longitude + longitude_delta,
        )

    @classmethod
    def _build_mock_trajectory(
        cls,
        center_latitude: float,
        center_longitude: float,
        release_time: datetime,
        mock_index: int,
    ) -> list[dict]:
        """
        Deterministic mock trajectory around the real culprit.

        These are ONLY for frontend visualization.
        They are not AIS observations and do not affect attribution.
        """

        base = (mock_index + 1) * 0.8

        offsets = [
            (-base, -0.4 * base),
            (-0.35 * base, 0.0),
            (0.0, 0.45 * base),
            (0.4 * base, 0.8 * base),
            (0.75 * base, 1.0 * base),
        ]

        trajectory = []

        for step, (north_km, east_km) in enumerate(offsets):
            latitude, longitude = cls._offset_point(
                center_latitude,
                center_longitude,
                north_km,
                east_km,
            )

            trajectory.append(
                {
                    "timestamp": release_time
                    + timedelta(hours=-2 + step),
                    "latitude": round(latitude, 6),
                    "longitude": round(longitude, 6),
                    "speed": None,
                    "course": None,
                    "heading": None,
                }
            )

        return trajectory

    @classmethod
    def _select_five_real_trajectory_points(
        cls,
        positions: list[Any],
        release_time: datetime,
    ) -> list[dict]:
        """
        Select exactly five representative AIS points.

        Target times:
            -2 hours
            -1 hour
             0 hours
            +1 hour
            +2 hours

        For each target time, select the closest available AIS point.

        This keeps the frontend response small while still showing
        the vessel's movement across the entire attribution window.
        """

        if not positions:
            return []

        target_times = [
            release_time + timedelta(hours=-2),
            release_time + timedelta(hours=-1),
            release_time,
            release_time + timedelta(hours=1),
            release_time + timedelta(hours=2),
        ]

        selected = []

        for target_time in target_times:
            closest = min(
                positions,
                key=lambda position: abs(
                    cls._ensure_utc(position.timestamp)
                    - target_time
                ),
            )

            selected.append(
                cls._position_to_dict(closest)
            )

        # Remove accidental duplicates while preserving order.
        result = []
        seen = set()

        for point in selected:
            key = point["timestamp"]

            if key in seen:
                continue

            seen.add(key)
            result.append(point)

        return result

    @classmethod
    def _find_nearest_to_origin(
        cls,
        positions: list[Any],
        origin_latitude: float,
        origin_longitude: float,
    ) -> tuple[dict | None, float | None]:
        """
        Find the AIS position spatially closest to the estimated
        backtrack origin.

        This is intentionally different from finding the AIS point
        closest in time to the release timestamp.

        The existing attribution result is NOT changed.
        This is only evidence generation.
        """

        if not positions:
            return None, None

        closest_position = min(
            positions,
            key=lambda position: DriftEngine.haversine_km(
                origin_latitude,
                origin_longitude,
                float(position.latitude),
                float(position.longitude),
            ),
        )

        closest_dict = cls._position_to_dict(
            closest_position
        )

        distance = DriftEngine.haversine_km(
            origin_latitude,
            origin_longitude,
            closest_dict["latitude"],
            closest_dict["longitude"],
        )

        return (
            closest_dict,
            round(distance, 3),
        )

    @classmethod
    def _find_nearest_to_release_time(
        cls,
        positions: list[Any],
        release_time: datetime,
    ) -> dict | None:
        """
        Find the AIS position closest in time to the estimated
        release timestamp.

        This is exposed for debugging/evidence comparison.
        """

        if not positions:
            return None

        closest_position = min(
            positions,
            key=lambda position: abs(
                cls._ensure_utc(position.timestamp)
                - release_time
            ),
        )

        return cls._position_to_dict(
            closest_position
        )

    async def build(
        self,
        db: AsyncSession,
        spill: dict,
        vessels: list,
    ) -> dict:
        """
        Build the evidence response for the exact vessels returned
        by the existing /vessels API.
        """

        release_time = self._ensure_utc(
            datetime.fromisoformat(
                spill["estimated_release_time"]
            )
        )

        # ------------------------------------------------------------
        # Backtrack origin
        # ------------------------------------------------------------

        origin_latitude = spill.get(
            "estimated_source_latitude"
        )

        origin_longitude = spill.get(
            "estimated_source_longitude"
        )

        if (
            origin_latitude is None
            or origin_longitude is None
        ):
            origin_latitude = spill[
                "observation_latitude"
            ]
            origin_longitude = spill[
                "observation_longitude"
            ]

        source_radius_km = spill.get(
            "estimated_source_radius_km"
        )

        # ------------------------------------------------------------
        # AIS trajectory window
        # ------------------------------------------------------------

        start_time = (
            release_time
            - timedelta(
                hours=self.TRAJECTORY_HALF_WINDOW_HOURS
            )
        )

        end_time = (
            release_time
            + timedelta(
                hours=self.TRAJECTORY_HALF_WINDOW_HOURS
            )
        )

        # ------------------------------------------------------------
        # Find the real vessel from the EXISTING vessel list.
        #
        # This is critical:
        # we do not perform attribution again.
        # ------------------------------------------------------------

        real_vessel = next(
            (
                vessel
                for vessel in vessels
                if not vessel.is_mock
            ),
            None,
        )

        real_vessel_id = (
            real_vessel.vessel_id
            if real_vessel
            else None
        )

        real_positions = []
        vessel_metadata = None

        if real_vessel_id:

            # PostgreSQL AIS only.
            real_positions = (
                await self.ais_repository
                .get_positions_for_vessel(
                    db=db,
                    vessel_id=real_vessel_id,
                    start_time=start_time,
                    end_time=end_time,
                    synthetic_only=True,
                    scenario_id=None,
                )
            )

            vessel_metadata = (
                await self.ais_repository.get_vessel(
                    db=db,
                    vessel_id=real_vessel_id,
                )
            )

        # ------------------------------------------------------------
        # TWO different AIS reference points
        # ------------------------------------------------------------

        # 1. Spatially closest AIS point to backtrack origin.
        #
        # This is used as the culprit/source-area evidence point.
        nearest_origin_position = None
        origin_distance = None

        if real_positions:
            (
                nearest_origin_position,
                origin_distance,
            ) = self._find_nearest_to_origin(
                real_positions,
                origin_latitude,
                origin_longitude,
            )

        # 2. Temporally closest AIS point to release time.
        #
        # This is kept separately so the frontend can expose/debug
        # the discrepancy in the synthetic AIS data.
        timestamp_nearest_position = (
            self._find_nearest_to_release_time(
                real_positions,
                release_time,
            )
            if real_positions
            else None
        )

        # ------------------------------------------------------------
        # Five-point real trajectory
        # ------------------------------------------------------------

        real_display_trajectory = (
            self._select_five_real_trajectory_points(
                real_positions,
                release_time,
            )
            if real_positions
            else []
        )

        # ------------------------------------------------------------
        # Mock vessels should be close to the real culprit.
        #
        # Use the origin-nearest real position as the center.
        # If no real AIS point exists, use the backtrack origin.
        # ------------------------------------------------------------

        center_latitude = (
            nearest_origin_position["latitude"]
            if nearest_origin_position
            else origin_latitude
        )

        center_longitude = (
            nearest_origin_position["longitude"]
            if nearest_origin_position
            else origin_longitude
        )

        result_vessels = []

        mock_index = 0

        for vessel in vessels:

            # Pydantic model -> dictionary
            if hasattr(vessel, "model_dump"):
                vessel_data = vessel.model_dump()
            else:
                vessel_data = dict(vessel)

            # ========================================================
            # REAL VESSEL
            # ========================================================

            if not vessel.is_mock:

                # Exactly five representative points for frontend.
                vessel_data[
                    "trajectory"
                ] = real_display_trajectory

                vessel_data[
                    "full_trajectory_point_count"
                ] = len(real_positions)

                vessel_data[
                    "country"
                ] = (
                    vessel_metadata.country
                    if vessel_metadata
                    else None
                )

                vessel_data[
                    "vessel_type"
                ] = (
                    vessel_metadata.shiptype_name
                    if vessel_metadata
                    else None
                )

                vessel_data[
                    "culprit_location"
                ] = nearest_origin_position

                vessel_data[
                    "distance_from_backtrack_origin_km"
                ] = origin_distance

                result_vessels.append(
                    vessel_data
                )

                continue

            # ========================================================
            # MOCK VESSEL
            # ========================================================

            mock_trajectory = (
                self._build_mock_trajectory(
                    center_latitude=center_latitude,
                    center_longitude=center_longitude,
                    release_time=release_time,
                    mock_index=mock_index,
                )
            )

            mock_index += 1

            mock_location = min(
                mock_trajectory,
                key=lambda point: abs(
                    point["timestamp"]
                    - release_time
                ),
            )

            mock_distance = (
                DriftEngine.haversine_km(
                    origin_latitude,
                    origin_longitude,
                    mock_location["latitude"],
                    mock_location["longitude"],
                )
            )

            vessel_data[
                "culprit_location"
            ] = mock_location

            vessel_data[
                "distance_from_backtrack_origin_km"
            ] = round(
                mock_distance,
                3,
            )

            vessel_data[
                "trajectory"
            ] = mock_trajectory

            vessel_data[
                "full_trajectory_point_count"
            ] = 5

            result_vessels.append(
                vessel_data
            )

        # ------------------------------------------------------------
        # Verification
        # ------------------------------------------------------------

        real_distance = next(
            (
                vessel[
                    "distance_from_backtrack_origin_km"
                ]
                for vessel in result_vessels
                if not vessel["is_mock"]
            ),
            None,
        )

        within_source_radius = None

        if (
            real_distance is not None
            and source_radius_km is not None
        ):
            within_source_radius = (
                real_distance
                <= source_radius_km
            )

        # ------------------------------------------------------------
        # Attribution score
        #
        # Normally comes from existing /vessels.
        # Fallback to catalog score if the vessel response has None.
        #
        # This does NOT rerun attribution.
        # ------------------------------------------------------------

        top_score = (
            real_vessel.score
            if real_vessel
            else None
        )

        if top_score is None:
            top_score = spill.get(
                "ranked_top_score"
            )

        # ------------------------------------------------------------
        # Return
        # ------------------------------------------------------------

        return {
            "spill_id": spill["spill_id"],

            "backtrack_origin": {
                "latitude": origin_latitude,
                "longitude": origin_longitude,
                "timestamp": release_time,
                "radius_km": source_radius_km,
            },

            "attribution": {
                "top_vessel": real_vessel_id,
                "top_score": top_score,
                "rank": (
                    real_vessel.rank
                    if real_vessel
                    else None
                ),
                "candidate_count": len(vessels),
            },

            "verification": {
                "culprit_vessel_id": real_vessel_id,

                # This is the AIS point closest spatially
                # to the backtracked source.
                "culprit_position_timestamp": (
                    nearest_origin_position[
                        "timestamp"
                    ]
                    if nearest_origin_position
                    else None
                ),

                "origin_to_culprit_distance_km": (
                    real_distance
                ),

                "within_backtrack_radius": (
                    within_source_radius
                ),

                "ais_points_in_window": len(
                    real_positions
                ),

                "display_trajectory_points": (
                    len(real_display_trajectory)
                ),

                "trajectory_window": {
                    "start": start_time,
                    "end": end_time,
                },

                # ----------------------------------------------------
                # DEBUG / EVIDENCE
                #
                # This makes the synthetic AIS discontinuity visible
                # to the frontend instead of hiding it.
                # ----------------------------------------------------

                "nearest_origin_ais_point": (
                    nearest_origin_position
                ),

                "timestamp_nearest_ais_point": (
                    timestamp_nearest_position
                ),

                "timestamp_nearest_distance_from_origin_km": (
                    round(
                        DriftEngine.haversine_km(
                            origin_latitude,
                            origin_longitude,
                            timestamp_nearest_position[
                                "latitude"
                            ],
                            timestamp_nearest_position[
                                "longitude"
                            ],
                        ),
                        3,
                    )
                    if timestamp_nearest_position
                    else None
                ),
            },

            "vessels": result_vessels,
        }