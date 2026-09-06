import pytest
from httpx import AsyncClient
from app.main import app
from app.services.spill_catalog_service import SpillCatalogService

# Initialize the catalog before tests run
SpillCatalogService.initialize()

@pytest.mark.asyncio
async def test_get_demo_spills():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/demo/spills")
    
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert data["total"] == SpillCatalogService.get_total_count()
    assert data["total"] > 0
    assert len(data["items"]) == 20  # Default page size

@pytest.mark.asyncio
async def test_get_demo_spill_detail():
    # Get a valid spill ID
    spills = SpillCatalogService.get_all_spills(limit=1)
    if not spills:
        pytest.skip("Catalog not initialized properly")
    spill_id = spills[0]["spill_id"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/demo/spills/{spill_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["spill_id"] == spill_id
    assert "centroid" in data
    assert "image_url" in data

@pytest.mark.asyncio
async def test_get_demo_spill_vessels():
    spills = SpillCatalogService.get_all_spills(limit=1)
    if not spills:
        pytest.skip("Catalog not initialized properly")
    spill_id = spills[0]["spill_id"]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/demo/spills/{spill_id}/vessels")
        
    assert response.status_code == 200
    data = response.json()
    assert data["spill_id"] == spill_id
    assert len(data["vessels"]) >= 3
    
    mock_vessels = [v for v in data["vessels"] if v["is_mock"]]
    assert len(mock_vessels) == 3


@pytest.mark.asyncio
async def test_get_demo_spill_343abc_vessels_mmsi_imo_compliance():
    """
    Validate that /api/v1/demo/spills/spill_343abc/vessels returns:
    - Exactly 9-digit MMSI following ITU-R M.585
    - Exactly 7-digit IMO with mathematically valid check digit according to IMO Resolution A.1078(28)
    """
    from app.services.mock_vessel_service import compute_imo_checksum

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/demo/spills/spill_343abc/vessels")

    assert response.status_code == 200
    data = response.json()
    assert data["spill_id"] == "spill_343abc"
    assert len(data["vessels"]) == 4

    for v in data["vessels"]:
        mmsi = v["mmsi"]
        imo = v["imo"]

        # MMSI: exactly 9 digits
        assert mmsi is not None
        assert len(mmsi) == 9
        assert mmsi.isdigit()

        # IMO: exactly 7 digits
        assert imo is not None
        assert len(imo) == 7
        assert imo.isdigit()

        # Check digit algorithm validation:
        first_6 = imo[:6]
        expected_check = compute_imo_checksum(first_6)
        actual_check = int(imo[6])
        assert actual_check == expected_check, f"Vessel {v['vessel_id']} IMO {imo} check digit failed"


@pytest.mark.asyncio
async def test_health_ready():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    
    assert response.status_code == 200
    assert response.json()["status"] in ["ready", "unready"]


@pytest.mark.asyncio
async def test_backtrack_spill_empty_candidates_handled_gracefully():
    """
    Validate that /demo/spills/{spill_id}/backtrack safely handles 0 candidates
    without raising IndexError, falling back cleanly to catalog ranked_top_score.
    """
    from unittest.mock import AsyncMock
    from app.routers.demo_spills import get_attribution_engine

    spills = SpillCatalogService.get_all_spills(limit=1)
    if not spills:
        pytest.skip("Catalog not initialized properly")
    spill_id = spills[0]["spill_id"]

    mock_engine = AsyncMock()
    mock_engine.attribute.return_value = {
        "candidate_count": 0,
        "top_prediction": None,
        "candidates": [],
        "source_estimate": {"latitude": 34.0, "longitude": 24.0, "radius_km": 5.0}
    }

    app.dependency_overrides[get_attribution_engine] = lambda: mock_engine
    try:
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(f"/api/v1/demo/spills/{spill_id}/backtrack")
        
        assert response.status_code == 200
        data = response.json()
        assert data["spill_id"] == spill_id
        assert data["attribution"]["candidate_count"] == 0
        assert data["attribution"]["top_vessel"] is None
        
        expected_score = spills[0].get("ranked_top_score")
        if expected_score is not None:
            assert data["attribution"]["top_score"] == float(expected_score)
        else:
            assert data["attribution"]["top_score"] is None
    finally:
        app.dependency_overrides.pop(get_attribution_engine, None)


