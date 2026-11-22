from __future__ import annotations

import json
import logging
from typing import Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    DemoPaginationResponse,
    DemoSpillListItem,
    DemoSpillDetail,
    DemoSpillVesselResponse,
    DemoAttributionTrajectoryResponse,
    SpillPredictionResponse,
    DemoBacktrackResponse,
    CentroidSchema,
)
from app.schemas.visualization import VisualizationResponse

logger = logging.getLogger(__name__)

class NeonSpillService:
    @staticmethod
    async def list_spills(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> Optional[DemoPaginationResponse]:
        """
        Query paginated spills from spills_catalog table.
        """
        try:
            skip = (page - 1) * page_size
            total_stmt = text("SELECT count(*) FROM spills_catalog")
            total_res = await db.execute(total_stmt)
            total = total_res.scalar() or 0

            if total == 0:
                return None

            items_stmt = text("""
                SELECT spill_id, detected_at, centroid_lat, centroid_lon, 
                       area_km2, confidence_score, candidate_count, image_url
                FROM spills_catalog
                ORDER BY detected_at DESC
                OFFSET :skip LIMIT :limit
            """)
            items_res = await db.execute(items_stmt, {"skip": skip, "limit": page_size})
            rows = items_res.fetchall()

            items = []
            for r in rows:
                items.append(
                    DemoSpillListItem(
                        spill_id=r.spill_id,
                        detected_at=r.detected_at,
                        centroid=CentroidSchema(lon=r.centroid_lon, lat=r.centroid_lat),
                        area_km2=r.area_km2,
                        confidence_score=r.confidence_score,
                        candidate_count=r.candidate_count,
                        image_url=r.image_url,
                    )
                )

            return DemoPaginationResponse(
                total=total,
                page=page,
                page_size=page_size,
                items=items,
            )
        except Exception:
            logger.exception("Failed to query list_spills from Neon")
            return None

    @staticmethod
    async def get_spill_detail(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[DemoSpillDetail]:
        """
        Query a single spill detail from spills_catalog.
        """
        try:
            stmt = text("SELECT detail_payload FROM spills_catalog WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return DemoSpillDetail(**payload)
        except Exception:
            logger.exception("Failed to query get_spill_detail for %s from Neon", spill_id)
        return None

    @staticmethod
    async def get_spill_vessels(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[DemoSpillVesselResponse]:
        """
        Query candidate vessels from spill_vessels table.
        """
        try:
            stmt = text("SELECT payload FROM spill_vessels WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return DemoSpillVesselResponse(**payload)
        except Exception:
            logger.exception("Failed to query get_spill_vessels for %s from Neon", spill_id)
        return None

    @staticmethod
    async def get_attribution_trajectory(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[DemoAttributionTrajectoryResponse]:
        """
        Query attribution evidence dossier from spill_attributions table.
        """
        try:
            stmt = text("SELECT payload FROM spill_attributions WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return DemoAttributionTrajectoryResponse(**payload)
        except Exception:
            logger.exception("Failed to query attribution trajectory for %s from Neon", spill_id)
        return None

    @staticmethod
    async def get_spill_forecast(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[SpillPredictionResponse]:
        """
        Query forward forecast trajectory from spill_forecasts table.
        """
        try:
            stmt = text("SELECT payload FROM spill_forecasts WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return SpillPredictionResponse(**payload)
        except Exception:
            logger.exception("Failed to query forward forecast for %s from Neon", spill_id)
        return None

    @staticmethod
    async def get_spill_backtrack(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[DemoBacktrackResponse]:
        """
        Query backtrack summary from spill_backtracks table.
        """
        try:
            stmt = text("SELECT payload FROM spill_backtracks WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return DemoBacktrackResponse(**payload)
        except Exception:
            logger.exception("Failed to query backtrack for %s from Neon", spill_id)
        return None

    @staticmethod
    async def get_spill_visualization(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[VisualizationResponse]:
        """
        Query visualization trajectory & environment from spill_visualizations table.
        """
        try:
            stmt = text("SELECT payload FROM spill_visualizations WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                payload = row[0]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return VisualizationResponse(**payload)
        except Exception:
            logger.exception("Failed to query visualization for %s from Neon", spill_id)
        return None

    @staticmethod
    async def get_diagnostic_plot_url(
        db: AsyncSession,
        spill_id: str,
    ) -> Optional[str]:
        """
        Query diagnostic plot Cloudinary URL from diagnostic_plots table.
        """
        try:
            stmt = text("SELECT plot_url FROM diagnostic_plots WHERE spill_id = :spill_id")
            res = await db.execute(stmt, {"spill_id": spill_id})
            row = res.fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            logger.exception("Failed to query diagnostic plot for %s from Neon", spill_id)
        return None
