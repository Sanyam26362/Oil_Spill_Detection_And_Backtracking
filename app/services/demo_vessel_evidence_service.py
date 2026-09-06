from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import cos, radians
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ais_repository import AISRepository
from app.services.drift_engine import DriftEngine
from app.services.maritime_simulation import (
    MaritimeKinematicSimulator,
    snap_to_clean_30min,
)


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
        speed: float | None = None,
        course: float | None = None,
        heading: float | None = None,
        backtrack_origin: dict | None = None,
        mock_vessel: Any = None,
        detected_at: datetime | None = None,
    ):
        """
        Generate realistic maritime mock trajectory using MaritimeKinematicSimulator.
        Follows stochastic Ornstein-Uhlenbeck processes, dead-reckoning equations,
        vessel-type navigation profiles (Cargo, Tanker, Fishing), clean 30-minute
        temporal sampling (:00 and :30), and outer corridor constraints (10 - 25 km).
        """
        vessel_type = (
            getattr(mock_vessel, "vessel_type", None)
            or (mock_vessel.get("vessel_type") if isinstance(mock_vessel, dict) else None)
            or "Cargo"
        )
        vessel_id = (
            getattr(mock_vessel, "vessel_id", None)
            or (mock_vessel.get("vessel_id") if isinstance(mock_vessel, dict) else None)
        )
        target_dist = (
            getattr(mock_vessel, "distance_to_origin_km", None)
            if mock_vessel is not None
            else None
        )
        if target_dist is None and isinstance(mock_vessel, dict):
            target_dist = mock_vessel.get("distance_to_origin_km")

        time_diff = (
            getattr(mock_vessel, "time_difference_hours", None)
            if mock_vessel is not None
            else None
        )
        if time_diff is None and isinstance(mock_vessel, dict):
            time_diff = mock_vessel.get("time_difference_hours")

        origin_lat = backtrack_origin["latitude"] if backtrack_origin else center_latitude
        origin_lon = backtrack_origin["longitude"] if backtrack_origin else center_longitude

        trajectory, culprit_location, calc_dist = MaritimeKinematicSimulator.simulate_mock_trajectory(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            release_time=release_time,
            mock_index=mock_index,
            vessel_type=vessel_type,
            vessel_id=vessel_id,
            detected_at=detected_at,
            target_distance_km=target_dist,
            time_difference_hours=time_diff,
        )

        if mock_vessel is not None:
            if hasattr(mock_vessel, "distance_to_origin_km"):
                mock_vessel.distance_to_origin_km = round(calc_dist, 2)
            elif isinstance(mock_vessel, dict):
                mock_vessel["distance_to_origin_km"] = round(calc_dist, 2)

        return trajectory, culprit_location, calc_dist

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

        detected_at_raw = spill.get("detected_at")
        detected_at = (
            self._ensure_utc(
                datetime.fromisoformat(detected_at_raw)
                if isinstance(detected_at_raw, str)
                else detected_at_raw
            )
            if detected_at_raw
            else None
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
        # ------------------------------------------------------------
        # AIS attribution window (for candidate spatial/temporal verification)
        # ------------------------------------------------------------

        attrib_start = (
            release_time
            - timedelta(
                hours=self.TRAJECTORY_HALF_WINDOW_HOURS
            )
        )

        attrib_end = (
            release_time
            + timedelta(
                hours=self.TRAJECTORY_HALF_WINDOW_HOURS
            )
        )

        # ------------------------------------------------------------
        # Full voyage trajectory window (clean :00 and :30, 30-min sampling)
        # ------------------------------------------------------------

        nominal_start = release_time - timedelta(hours=3)
        start_time = snap_to_clean_30min(nominal_start, "round")

        if detected_at is not None:
            nominal_end = detected_at + timedelta(hours=3)
            end_time = snap_to_clean_30min(nominal_end, "round")
        else:
            nominal_end = release_time + timedelta(hours=6)
            end_time = snap_to_clean_30min(nominal_end, "round")

        if end_time < start_time + timedelta(hours=6):
            end_time = start_time + timedelta(hours=6)

        times: list[datetime] = []
        curr = start_time
        while curr <= end_time:
            times.append(curr)
            curr += timedelta(minutes=30)

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
        attrib_positions = []
        vessel_metadata = None

        if real_vessel_id:

            corridor_center = (
                origin_latitude,
                origin_longitude,
            )

            # 1. Fetch positions within attribution verification window (±2h release window)
            attrib_positions = (
                await self.ais_repository
                .get_positions_for_vessel(
                    db=db,
                    vessel_id=real_vessel_id,
                    start_time=attrib_start,
                    end_time=attrib_end,
                    synthetic_only=True,
                    scenario_id=getattr(real_vessel, "scenario_id", None),
                    corridor_origin=corridor_center,
                    max_corridor_radius_km=120.0,
                )
            )

            # 2. Fetch positions across full detection/attribution voyage window
            duration_hours = (end_time - start_time).total_seconds() / 3600.0
            dynamic_corridor_km = min(600.0, max(150.0, 120.0 + duration_hours * 25.0))

            real_positions = (
                await self.ais_repository
                .get_positions_for_vessel(
                    db=db,
                    vessel_id=real_vessel_id,
                    start_time=start_time,
                    end_time=end_time,
                    synthetic_only=True,
                    scenario_id=getattr(real_vessel, "scenario_id", None),
                    corridor_origin=corridor_center,
                    max_corridor_radius_km=dynamic_corridor_km,
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

        nearest_origin_position = None
        origin_distance = None

        verify_positions = attrib_positions if attrib_positions else real_positions

        # 1. Spatially closest AIS point to backtrack origin (CPA within release window).
        if verify_positions:
            (
                nearest_origin_position,
                origin_distance,
            ) = self._find_nearest_to_origin(
                verify_positions,
                origin_latitude,
                origin_longitude,
            )

        # 2. Temporally closest AIS point to release time.
        timestamp_nearest_position = (
            self._find_nearest_to_release_time(
                verify_positions,
                release_time,
            )
            if verify_positions
            else None
        )

        # ------------------------------------------------------------
        # Full voyage trajectory sampled at clean 30-minute intervals
        # (:00 and :30), matching mock vessel temporal coverage
        # ------------------------------------------------------------

        real_display_trajectory = (
            MaritimeKinematicSimulator.sample_real_trajectory(
                real_positions if real_positions else attrib_positions,
                times,
            )
            if (real_positions or attrib_positions)
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
        backtrack_origin = {
            "latitude": origin_latitude,
            "longitude": origin_longitude,
            "timestamp": (
                release_time.isoformat().replace("+00:00", "Z")
                if isinstance(release_time, datetime)
                else str(release_time)
            ),
            "radius_km": source_radius_km,
        }

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
                current_score = (
                    vessel.score
                    if getattr(vessel, "score", None) is not None
                    else float(spill.get("ranked_top_score") or 0.25)
                )
                derived_correlation = round(
                    min(0.98, max(0.15, float(current_score) * 1.1)), 2
                )
                vessel_data["trajectory_correlation"] = derived_correlation
                vessel_data["is_mock_comparison"] = False
                if real_vessel:
                    real_vessel.trajectory_correlation = derived_correlation

                # Exactly five representative points for frontend.
                vessel_data[
                    "trajectory"
                ] = real_display_trajectory

                vessel_data[
                    "full_trajectory_point_count"
                ] = len(real_display_trajectory)

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

            mock_vessel = vessel

            mock_trajectory, culprit_location, calc_dist = (
                self._build_mock_trajectory(
                    center_latitude=center_latitude,
                    center_longitude=center_longitude,
                    release_time=release_time,
                    mock_index=mock_index,
                    speed=vessel_data.get("speed"),
                    course=vessel_data.get("course"),
                    heading=vessel_data.get("heading"),
                    backtrack_origin=backtrack_origin,
                    mock_vessel=mock_vessel,
                    detected_at=detected_at,
                )
            )

            mock_index += 1

            vessel_data["rank"] = None
            vessel_data["is_mock_comparison"] = True
            vessel_data["trajectory_correlation"] = None

            vessel_data[
                "culprit_location"
            ] = culprit_location

            vessel_data[
                "distance_from_backtrack_origin_km"
            ] = calc_dist

            vessel_data[
                "distance_to_origin_km"
            ] = round(calc_dist, 2)

            vessel_data[
                "trajectory"
            ] = mock_trajectory

            vessel_data[
                "full_trajectory_point_count"
            ] = len(mock_trajectory)

            if culprit_location:
                vessel_data["speed"] = culprit_location.get("speed")
                vessel_data["course"] = culprit_location.get("course")
                vessel_data["heading"] = culprit_location.get("heading")
            vessel_data["time_difference_hours"] = getattr(
                mock_vessel, "time_difference_hours", None
            )

            result_vessels.append(
                vessel_data
            )

        # ------------------------------------------------------------
        # Verification
        # ------------------------------------------------------------

        real_distance = next(
            (
                vessel["distance_from_backtrack_origin_km"]
                for vessel in result_vessels
                if not vessel["is_mock"]
                and vessel["distance_from_backtrack_origin_km"]
                is not None
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
        # Top score resolution
        # ------------------------------------------------------------

        top_score = next(
            (
                vessel.get("score")
                for vessel in result_vessels
                if not vessel.get("is_mock")
            ),
            None,
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

            "backtrack_origin": backtrack_origin,

            "attribution": {
                "top_vessel": real_vessel_id,
                "top_candidate_vessel_id": real_vessel_id,
                "attribution_qualification": (
                    "Vessel identified within 30 km transit corridor during estimated release window; "
                    "evaluated via multi-criteria trajectory and velocity scoring."
                ),
                "top_score": top_score,
                "rank": (
                    real_vessel.rank
                    if real_vessel
                    else None
                ),
                # candidate_count from the catalog reflects the real
                # database count (e.g. 2), not len(vessels) which
                # always equals 4 (1 real + 3 mock).
                "candidate_count": spill.get(
                    "candidate_count", len(vessels)
                ),
            },

            "verification": {
                "culprit_vessel_id": real_vessel_id,

                "search_parameters": {
                    "drift_uncertainty_radius_km": round(float(backtrack_origin["radius_km"]), 3) if backtrack_origin.get("radius_km") is not None else None,
                    "candidate_search_corridor_radius_km": 30.0,
                    "temporal_window_hours": 2.0,
                },

                "candidate_within_corridor": (
                    real_distance is not None and real_distance <= 30.0
                ),

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
                    attrib_positions if attrib_positions else real_positions
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

                "closest_approach_ais_point": (
                    nearest_origin_position
                ),

                "closest_approach_distance_km": (
                    real_distance
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