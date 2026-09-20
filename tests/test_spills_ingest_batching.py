import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy import delete

from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.spill import OilSpillDetection


@pytest.mark.asyncio
async def test_spills_ingest_batching_order_and_counts():
    """
    Test that /api/v1/spills/ingest-ml performs batched insertion
    and preserves both the list contents and their exact order for
    inserted_spill_ids and skipped_spill_ids.
    """
    test_ids = [
        "batch_test_01",
        "batch_test_02",
        "batch_test_03",
        "batch_test_04",
        "batch_test_05",
    ]

    # Clean up before and after
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(OilSpillDetection).where(OilSpillDetection.spill_id.in_(test_ids))
            )
            await session.commit()
    except Exception:
        pytest.skip("Database not available")

    try:
        def make_item(spill_id: str):
            return {
                "spill_id": spill_id,
                "detected_at": datetime(2019, 7, 15, 12, 0, tzinfo=timezone.utc).isoformat(),
                "centroid": {"lat": 34.0, "lon": 25.0},
                "polygon": [[25.0, 34.0], [25.1, 34.0], [25.1, 34.1], [25.0, 34.0]],
                "area_km2": 1.5,
                "estimated_age_hours": 10.0,
                "confidence_score": 0.95,
                "image_reference": f"https://res.cloudinary.com/test/{spill_id}.png",
            }

        # Step 1: Pre-populate batch_test_01 and batch_test_03
        pre_payload = {
            "detections": [
                make_item("batch_test_01"),
                make_item("batch_test_03"),
            ]
        }
        async with AsyncClient(app=app, base_url="http://test") as ac:
            res1 = await ac.post("/api/v1/spills/ingest-ml", json=pre_payload)
            assert res1.status_code == 201
            data1 = res1.json()
            assert data1["inserted_count"] == 2
            assert data1["skipped_count"] == 0
            assert data1["inserted_spill_ids"] == ["batch_test_01", "batch_test_03"]
            assert data1["skipped_spill_ids"] == []

            # Step 2: Post payload with interleaved existing and new items
            # Order: 01 (exists), 02 (new), 03 (exists), 04 (new), 05 (new)
            mixed_payload = {
                "detections": [
                    make_item("batch_test_01"),
                    make_item("batch_test_02"),
                    make_item("batch_test_03"),
                    make_item("batch_test_04"),
                    make_item("batch_test_05"),
                ]
            }
            res2 = await ac.post("/api/v1/spills/ingest-ml", json=mixed_payload)
            assert res2.status_code == 201
            data2 = res2.json()

            # Verify counts
            assert data2["inserted_count"] == 3
            assert data2["skipped_count"] == 2

            # Verify contents and exact sequential ordering
            assert data2["inserted_spill_ids"] == ["batch_test_02", "batch_test_04", "batch_test_05"]
            assert data2["skipped_spill_ids"] == ["batch_test_01", "batch_test_03"]

    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(OilSpillDetection).where(OilSpillDetection.spill_id.in_(test_ids))
            )
            await session.commit()
