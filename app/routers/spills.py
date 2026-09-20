from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.spill import OilSpillDetection
from app.models.schemas import (
    MLPredictionPayload,
    SpillDetectionItem,
)
from app.repositories.spill_repository import SpillRepository


router = APIRouter()


@router.post(
    "/ingest-ml",
    status_code=status.HTTP_201_CREATED,
)
async def ingest_ml_detections(
    payload: MLPredictionPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest real ML detection JSON.

    One JSON file may contain multiple detections.
    Each spill_id becomes an independent database row.
    """
    if not payload.detections:
        return {
            "message": "ML detections processed successfully.",
            "inserted_count": 0,
            "skipped_count": 0,
            "inserted_spill_ids": [],
            "skipped_spill_ids": [],
        }

    # E5: One batched existence query instead of per-detection SELECTs.
    all_ids = [d.spill_id for d in payload.detections]
    existing_result = await db.execute(
        select(OilSpillDetection.spill_id).where(
            OilSpillDetection.spill_id.in_(all_ids)
        )
    )
    existing_ids: set[str] = {row[0] for row in existing_result.fetchall()}

    inserted_spills = []
    skipped_spills = []
    new_spill_objects = []

    for detection in payload.detections:
        if detection.spill_id in existing_ids:
            skipped_spills.append(detection.spill_id)
            continue

        new_spill_objects.append(
            OilSpillDetection(
                spill_id=detection.spill_id,
                detected_at=detection.detected_at,
                centroid_lat=detection.centroid.lat,
                centroid_lon=detection.centroid.lon,
                polygon=detection.polygon,
                area_km2=detection.area_km2,
                estimated_age_hours=detection.estimated_age_hours,
                confidence_score=detection.confidence_score,
                cloudinary_url=(
                    getattr(detection, "image_reference", None)
                    or getattr(detection, "cloudinary_url", "")
                ),
                source_image_id=None,
                raw_prediction=detection.model_dump(mode="json"),
            )
        )
        inserted_spills.append(detection.spill_id)

    if new_spill_objects:
        db.add_all(new_spill_objects)
        await db.commit()

    return {
        "message": "ML detections processed successfully.",
        "inserted_count": len(inserted_spills),
        "skipped_count": len(skipped_spills),
        "inserted_spill_ids": inserted_spills,
        "skipped_spill_ids": skipped_spills,
    }


@router.get(
    "",
    response_model=list[SpillDetectionItem],
)
async def get_all_spills(
    db: AsyncSession = Depends(get_db),
):
    """
    Return all detected oil spills.

    Used by the frontend to initialize the map.
    """

    spills = (
        await SpillRepository.get_all_spills(
            db
        )
    )

    return [
        SpillDetectionItem(
            spill_id=spill.spill_id,

            detected_at=spill.detected_at,

            centroid={
                "lat": spill.centroid_lat,
                "lon": spill.centroid_lon,
            },

            polygon=spill.polygon,

            area_km2=spill.area_km2,

            estimated_age_hours=(
                spill.estimated_age_hours
            ),

            confidence_score=(
                spill.confidence_score
            ),

            image_reference=(
                spill.cloudinary_url
            ),
        )
        for spill in spills
    ]


@router.get(
    "/{spill_id}",
    response_model=SpillDetectionItem,
)
async def get_spill_details(
    spill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return one spill for the frontend detail panel.
    """

    spill = await SpillRepository.get_spill(
        db,
        spill_id,
    )

    if spill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spill not found",
        )

    return SpillDetectionItem(
        spill_id=spill.spill_id,

        detected_at=spill.detected_at,

        centroid={
            "lat": spill.centroid_lat,
            "lon": spill.centroid_lon,
        },

        polygon=spill.polygon,

        area_km2=spill.area_km2,

        estimated_age_hours=(
            spill.estimated_age_hours
        ),

        confidence_score=(
            spill.confidence_score
        ),

        image_reference=(
            spill.cloudinary_url
        ),
    )