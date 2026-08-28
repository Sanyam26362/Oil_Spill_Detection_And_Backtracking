from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ais import AISPosition, Vessel


class AISRepository:
    """
    Database access layer for AIS data.

    Responsibilities:
        - spatial candidate search
        - AIS trajectory retrieval
        - vessel metadata retrieval

    Business/scoring logic does not belong here.
    """

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
    ) -> list[AISPosition]:
        """
        Return chronologically ordered AIS positions
        for one vessel.
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

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    async def get_positions_for_vessels(
        self,
        db: AsyncSession,
        vessel_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        synthetic_only: bool | None = None,
        scenario_id: str | None = None,
    ) -> list[AISPosition]:
        """
        Return AIS observations for multiple vessels,
        ordered by vessel and timestamp.
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

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

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