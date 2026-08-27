from fastapi import HTTPException, status
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, Polygon
from shapely.validation import explain_validity
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import SpillIngestSchema
from app.models.spill import OilSpill
from app.repositories.spill_repository import SpillRepository


class SpillService:
    @staticmethod
    async def process_and_store_spill(
        spill_data: SpillIngestSchema,
        db: AsyncSession,
    ) -> OilSpill:

        # Create Shapely geometries
        centroid_geom = Point(
            spill_data.centroid.lon,
            spill_data.centroid.lat,
        )

        polygon_geom = Polygon(spill_data.polygon)

        # Validate polygon
        if polygon_geom.is_empty:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Spill polygon cannot be empty.",
            )

        if not polygon_geom.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Invalid spill polygon: "
                    f"{explain_validity(polygon_geom)}"
                ),
            )

        # Convert Shapely geometry to GeoAlchemy2 geometry
        db_data = {
            "spill_id": spill_data.spill_id,
            "detected_at": spill_data.detected_at,
            "centroid": from_shape(
                centroid_geom,
                srid=4326,
            ),
            "polygon": from_shape(
                polygon_geom,
                srid=4326,
            ),
            "area_km2": spill_data.area_km2,
            "estimated_age_hours": spill_data.estimated_age_hours,
            "confidence_score": spill_data.confidence_score,
        }

        try:
            return await SpillRepository.create_spill(
                db,
                db_data,
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to ingest spill data.",
            )