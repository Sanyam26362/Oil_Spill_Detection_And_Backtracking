from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ais import AISPosition, Vessel

EARTH_RADIUS_M = 6_371_000.0


class AISRepository:
    """
    Database access layer for AIS data.

    Responsibilities:
        - spatial candidate search
        - AIS trajectory retrieval
        - vessel metadata retrieval

    Business/scoring logic does not belong here.
    """

    @staticmethod
    def _haversine_distance_m(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Great-circle distance in metres between two (lat, lon) coordinates."""
        r_lat1 = math.radians(float(lat1))
        r_lat2 = math.radians(float(lat2))
        dlat = r_lat2 - r_lat1
        dlon = math.radians(float(lon2) - float(lon1))

        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(r_lat1)
            * math.cos(r_lat2)
            * math.sin(dlon / 2.0) ** 2
        )
        return (
            2.0
            * EARTH_RADIUS_M
            * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        )

    # ------------------------------------------------------------------
    # Teleportation spike filter
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_teleportation_spikes(
        positions: list[AISPosition],
        max_speed_ms: float = 18.0,
        corridor_origin: tuple[float, float] | None = None,
        max_corridor_radius_km: float = 120.0,
    ) -> list[AISPosition]:
        """
        Remove AIS pings that imply physically impossible vessel speeds.

        The positions list must already be ordered by timestamp ascending
        (as guaranteed by all callers in this repository).

        A ping is discarded when the implied displacement velocity
        relative to the *previous accepted* ping exceeds `max_speed_ms`
        (default 18 m/s ≈ 35 knots).

        If `corridor_origin` is provided, drop any leading ping that exceeds
        `max_corridor_radius_km` from `corridor_origin` so rogue pings outside
        the operational basin are rejected before velocity stepping begins.

        This eliminates cross-scenario coordinate jumps that occur when
        synthetic vessels share an ID across geographically separated
        Mediterranean sub-scenarios.
        """

        if not positions:
            return positions

        start_idx = 0
        if corridor_origin is not None:
            origin_lat, origin_lon = corridor_origin
            max_dist_m = max_corridor_radius_km * 1000.0
            while start_idx < len(positions):
                p = positions[start_idx]
                dist_m = AISRepository._haversine_distance_m(
                    origin_lat, origin_lon, p.latitude, p.longitude
                )
                if dist_m <= max_dist_m:
                    break
                start_idx += 1

            if start_idx >= len(positions):
                return []

        kept: list[AISPosition] = [positions[start_idx]]

        for ping in positions[start_idx + 1:]:
            prev = kept[-1]

            dt_seconds = (
                ping.timestamp - prev.timestamp
            ).total_seconds()

            # Identical or backward timestamps → keep (no movement implied).
            if dt_seconds <= 0:
                kept.append(ping)
                continue

            # Great-circle distance in metres between consecutive pings.
            distance_m = AISRepository._haversine_distance_m(
                prev.latitude, prev.longitude, ping.latitude, ping.longitude
            )

            implied_speed_ms = distance_m / dt_seconds

            if implied_speed_ms <= max_speed_ms:
                if corridor_origin is not None:
                    origin_lat, origin_lon = corridor_origin
                    dist_m = AISRepository._haversine_distance_m(
                        origin_lat, origin_lon, ping.latitude, ping.longitude
                    )
                    if dist_m > max_corridor_radius_km * 1000.0:
                        continue
                kept.append(ping)

        return kept

    async def get_candidate_vessels(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        radius_km: float,
        start_time: datetime,
        end_time: datetime,
        synthetic_only: bool | None = None,
        scenario_id: str | None = None,
    ) -> list[str]:
        """
        Find unique vessels observed inside a spatial and
        temporal search window.

        PostGIS performs the spatial filtering.
        """

        if radius_km <= 0:
            raise ValueError(
                "radius_km must be greater than 0."
            )

        if start_time > end_time:
            raise ValueError(
                "start_time must be <= end_time."
            )

        radius_m = radius_km * 1000.0

        conditions = [
            '"timestamp" BETWEEN :start_time AND :end_time',
            """
            ST_DWithin(
                geometry::geography,
                ST_SetSRID(
                    ST_MakePoint(
                        :longitude,
                        :latitude
                    ),
                    4326
                )::geography,
                :radius_m
            )
            """,
        ]

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": radius_m,
            "start_time": start_time,
            "end_time": end_time,
        }

        if synthetic_only is not None:
            conditions.append(
                "is_synthetic = :synthetic_only"
            )
            params["synthetic_only"] = synthetic_only

        if scenario_id is not None:
            conditions.append(
                "scenario_id = :scenario_id"
            )
            params["scenario_id"] = scenario_id

        where_clause = " AND ".join(
            conditions
        )

        query = text(
            f"""
            SELECT DISTINCT vessel_id
            FROM ais_positions
            WHERE {where_clause}
            ORDER BY vessel_id
            """
        )

        result = await db.execute(
            query,
            params,
        )

        return [
            row[0]
            for row in result.fetchall()
        ]

    async def get_positions_for_vessel(
        self,
        db: AsyncSession,
        vessel_id: str,
        start_time: datetime,
        end_time: datetime,
        synthetic_only: bool | None = None,
        scenario_id: str | None = None,
        corridor_origin: tuple[float, float] | None = None,
        max_corridor_radius_km: float = 120.0,
    ) -> list[AISPosition]:
        """
        Return chronologically ordered AIS positions for one vessel.

        Optional corridor bounding
        --------------------------
        When `corridor_origin` is supplied as a (latitude, longitude)
        tuple, only pings within `max_corridor_radius_km` of that point
        are returned.  This prevents coordinate jumps caused by
        synthetic vessels that share an ID across geographically
        separated sub-scenarios.

        Teleportation spike filter
        --------------------------
        After the database query a speed-based filter discards any ping
        that implies a displacement velocity > 18 m/s (≈ 35 knots)
        relative to the previous accepted ping.
        """

        if start_time > end_time:
            raise ValueError(
                "start_time must be <= end_time."
            )

        conditions = [
            AISPosition.vessel_id == vessel_id,
            AISPosition.timestamp >= start_time,
            AISPosition.timestamp <= end_time,
        ]

        if synthetic_only is not None:
            conditions.append(
                AISPosition.is_synthetic
                == synthetic_only
            )

        if scenario_id is not None:
            conditions.append(
                AISPosition.scenario_id == scenario_id
            )

        stmt = (
            select(AISPosition)
            .where(*conditions)
            .order_by(
                AISPosition.timestamp.asc()
            )
        )

        # Apply PostGIS corridor bounding when requested.
        if corridor_origin is not None:
            origin_lat, origin_lon = corridor_origin
            radius_m = max_corridor_radius_km * 1000.0
            corridor_clause = text(
                """
                ST_DWithin(
                    geometry::geography,
                    ST_SetSRID(
                        ST_Point(:origin_lon, :origin_lat),
                        4326
                    )::geography,
                    :max_corridor_radius_m
                )
                """
            ).bindparams(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                max_corridor_radius_m=radius_m,
            )
            stmt = stmt.where(corridor_clause)

        result = await db.execute(stmt)

        positions = list(result.scalars().all())

        # Post-query speed filter to drop teleportation spikes.
        return self._filter_teleportation_spikes(
            positions,
            corridor_origin=corridor_origin,
            max_corridor_radius_km=max_corridor_radius_km,
        )

    async def get_positions_for_vessels(
        self,
        db: AsyncSession,
        vessel_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        synthetic_only: bool | None = None,
        scenario_id: str | None = None,
        corridor_origin: tuple[float, float] | None = None,
        max_corridor_radius_km: float = 120.0,
    ) -> list[AISPosition]:
        """
        Return AIS observations for multiple vessels,
        ordered by vessel and timestamp.

        Optional corridor bounding
        --------------------------
        When `corridor_origin` is supplied as a (latitude, longitude)
        tuple, only pings within `max_corridor_radius_km` of that point
        are returned.  The speed-based teleportation spike filter is
        applied per-vessel after the query.
        """

        if not vessel_ids:
            return []

        if start_time > end_time:
            raise ValueError(
                "start_time must be <= end_time."
            )

        conditions = [
            AISPosition.vessel_id.in_(vessel_ids),
            AISPosition.timestamp >= start_time,
            AISPosition.timestamp <= end_time,
        ]

        if synthetic_only is not None:
            conditions.append(
                AISPosition.is_synthetic
                == synthetic_only
            )

        if scenario_id is not None:
            conditions.append(
                AISPosition.scenario_id == scenario_id
            )

        stmt = (
            select(AISPosition)
            .where(*conditions)
            .order_by(
                AISPosition.vessel_id.asc(),
                AISPosition.timestamp.asc(),
            )
        )

        # Apply PostGIS corridor bounding when requested.
        if corridor_origin is not None:
            origin_lat, origin_lon = corridor_origin
            radius_m = max_corridor_radius_km * 1000.0
            corridor_clause = text(
                """
                ST_DWithin(
                    geometry::geography,
                    ST_SetSRID(
                        ST_Point(:origin_lon, :origin_lat),
                        4326
                    )::geography,
                    :max_corridor_radius_m
                )
                """
            ).bindparams(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                max_corridor_radius_m=radius_m,
            )
            stmt = stmt.where(corridor_clause)

        result = await db.execute(stmt)
        all_positions = list(result.scalars().all())

        # Apply per-vessel teleportation spike filter.
        # Positions are already sorted by (vessel_id, timestamp).
        if not all_positions:
            return all_positions

        filtered: list[AISPosition] = []
        current_vessel_positions: list[AISPosition] = []
        current_vessel_id: str | None = None

        for pos in all_positions:
            if pos.vessel_id != current_vessel_id:
                if current_vessel_positions:
                    filtered.extend(
                        self._filter_teleportation_spikes(
                            current_vessel_positions,
                            corridor_origin=corridor_origin,
                            max_corridor_radius_km=max_corridor_radius_km,
                        )
                    )
                current_vessel_positions = [pos]
                current_vessel_id = pos.vessel_id
            else:
                current_vessel_positions.append(pos)

        # Flush the final vessel group.
        if current_vessel_positions:
            filtered.extend(
                self._filter_teleportation_spikes(
                    current_vessel_positions,
                    corridor_origin=corridor_origin,
                    max_corridor_radius_km=max_corridor_radius_km,
                )
            )

        return filtered

    async def get_vessel(
        self,
        db: AsyncSession,
        vessel_id: str,
    ) -> Vessel | None:
        """
        Retrieve vessel metadata, when available.
        """

        stmt = select(Vessel).where(
            Vessel.vessel_id == vessel_id
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()
