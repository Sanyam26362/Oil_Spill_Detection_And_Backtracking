import asyncio
from pathlib import Path
import pytest
from httpx import AsyncClient

from app.main import app
from app.services.spill_catalog_service import SpillCatalogService
from app.services.weather_service import WeatherService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEATHER_DIR = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
OCEAN_DIR = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"


@pytest.fixture(autouse=True)
def ensure_app_state():
    """Ensure app.state.weather_service and SpillCatalogService are initialized."""
    SpillCatalogService.initialize()
    if not hasattr(app.state, "weather_service") or app.state.weather_service is None:
        app.state.weather_service = WeatherService(
            weather_yearly_dir=WEATHER_DIR,
            ocean_yearly_dir=OCEAN_DIR,
            cache_max_months=3,
        )
    yield


@pytest.mark.asyncio
async def test_concurrent_requests_across_routers_no_closed_dataset():
    """
    D2: Verify that concurrent requests across different routers
    (/api/v1/drift/forward and /api/v1/visualization/spills/{id})
    both succeed and neither encounters a closed dataset or teardown error.
    """
    spills = SpillCatalogService.get_all_spills(limit=1)
    assert len(spills) > 0
    spill_id = spills[0]["spill_id"]

    drift_payload = {
        "start_latitude": 35.0,
        "start_longitude": 24.0,
        "start_time": "2019-07-15T12:00:00Z",
        "duration_hours": 1.0,
    }

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Fire both requests concurrently
        res_drift, res_vis = await asyncio.gather(
            ac.post("/api/v1/drift/forward", json=drift_payload),
            ac.get(f"/api/v1/visualization/spills/{spill_id}"),
        )

        assert res_drift.status_code == 200, f"Drift forward failed: {res_drift.text}"
        assert res_vis.status_code == 200, f"Visualization failed: {res_vis.text}"

        data_drift = res_drift.json()
        assert "end_latitude" in data_drift
        assert "end_longitude" in data_drift

        data_vis = res_vis.json()
        assert data_vis["spill"]["spill_id"] == spill_id
        assert "trajectory" in data_vis
        assert len(data_vis["trajectory"]) > 0

        # Run a second sequential request immediately after to confirm
        # the singleton weather_service was not closed by either router
        res_vis_after = await ac.get(f"/api/v1/visualization/spills/{spill_id}")
        assert res_vis_after.status_code == 200, f"Subsequent visualization request failed: {res_vis_after.text}"

        res_drift_after = await ac.post("/api/v1/drift/forward", json=drift_payload)
        assert res_drift_after.status_code == 200, f"Subsequent drift request failed: {res_drift_after.text}"
