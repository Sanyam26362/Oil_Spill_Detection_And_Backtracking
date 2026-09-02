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
    # The total should be 97 if initialization succeeded
    assert data["total"] == 97
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
async def test_health_ready():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    
    assert response.status_code == 200
    assert response.json()["status"] in ["ready", "unready"]
