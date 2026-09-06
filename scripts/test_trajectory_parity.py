import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.spill_catalog_service import SpillCatalogService

async def check():
    SpillCatalogService.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for sid in ["spill_5bcb47", "spill_4d67fb", "spill_75bc16"]:
            r = await client.get(f"/api/v1/demo/spills/{sid}/attribution/trajectory")
            assert r.status_code == 200, r.text
            data = r.json()
            print(f"\n=== {sid} ===")
            print("Attribution:", data["attribution"])
            print("Verification display points:", data["verification"]["display_trajectory_points"])
            print("Verification closest approach dist:", data["verification"]["closest_approach_distance_km"])
            v0 = data["vessels"][0]
            pts0 = v0["trajectory"]
            print(f"Real vessel {v0['vessel_id']} ({v0['vessel_type']}): {len(pts0)} points")
            print(f"  First: {pts0[0]['timestamp']} | lat={pts0[0]['latitude']}, lon={pts0[0]['longitude']}")
            print(f"  Last:  {pts0[-1]['timestamp']} | lat={pts0[-1]['latitude']}, lon={pts0[-1]['longitude']}")
            
            mock1 = data["vessels"][1]
            print(f"Mock vessel 1 ({mock1['vessel_type']}): {len(mock1['trajectory'])} points")
            assert len(pts0) == len(mock1["trajectory"]), f"Length mismatch: real {len(pts0)} vs mock {len(mock1['trajectory'])}"

if __name__ == "__main__":
    asyncio.run(check())
