from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import SpillIngestSchema
from app.services.spill_service import SpillService


router = APIRouter()


@router.post(
    "/ingest",
    status_code=status.HTTP_201_CREATED,
)
async def ingest_oil_spill(
    spill_data: SpillIngestSchema,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest an oil-spill detection produced by the ML pipeline.
    """

    spill = await SpillService.process_and_store_spill(
        spill_data,
        db,
    )

    return {
        "message": "Spill data ingested successfully.",
        "spill_id": spill.spill_id,
    }