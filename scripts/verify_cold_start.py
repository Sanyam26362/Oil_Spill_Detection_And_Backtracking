import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.spill_catalog_service import SpillCatalogService

async def main():
    # Force fresh catalog initialization (cold boot simulation)
    SpillCatalogService._initialized = False
    SpillCatalogService._spills = {}
    SpillCatalogService.initialize()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /demo/spills/spill_75bc16
        r_detail = await client.get("/api/v1/demo/spills/spill_75bc16")
        assert r_detail.status_code == 200, r_detail.text
        d = r_detail.json()
        print("1. GET /demo/spills/spill_75bc16:")
        print("   candidate_count:", d.get("candidate_count"))
        print("   ranked_top_vessel:", d.get("ranked_top_vessel"))
        print("   ranked_top_score:", d.get("ranked_top_score"))

        assert d["candidate_count"] == 1
        assert d["ranked_top_vessel"] == "SYNTH-Y2019-000019"
        assert d["ranked_top_score"] == 0.3007

        # 2. GET /demo/spills/spill_75bc16/vessels
        r_vessels = await client.get("/api/v1/demo/spills/spill_75bc16/vessels")
        assert r_vessels.status_code == 200, r_vessels.text
        v_data = r_vessels.json()
        print("\n2. GET /demo/spills/spill_75bc16/vessels:")
        vessels = v_data["vessels"]
        print(f"   real vessel: id={vessels[0]['vessel_id']}, rank={vessels[0]['rank']}, score={vessels[0]['score']}, correlation={vessels[0]['trajectory_correlation']}, is_mock_comparison={vessels[0].get('is_mock_comparison')}")
        assert vessels[0]["rank"] == 1
        assert vessels[0]["score"] == 0.3007
        assert vessels[0]["is_mock_comparison"] is False
        assert vessels[0]["trajectory_correlation"] == 0.33  # 0.3007 * 1.1 = 0.33

        for i, mv in enumerate(vessels[1:], 1):
            print(f"   mock {i}: id={mv['vessel_id']}, rank={mv['rank']}, score={mv['score']}, correlation={mv['trajectory_correlation']}, is_mock_comparison={mv.get('is_mock_comparison')}")
            assert mv["rank"] is None
            assert mv["score"] is None
            assert mv["is_mock_comparison"] is True
            assert mv["trajectory_correlation"] is None

        # 3. GET /demo/spills/spill_75bc16/attribution/trajectory
        r_traj = await client.get("/api/v1/demo/spills/spill_75bc16/attribution/trajectory")
        assert r_traj.status_code == 200, r_traj.text
        t_data = r_traj.json()
        print("\n3. GET /demo/spills/spill_75bc16/attribution/trajectory:")
        print("   attribution:", t_data["attribution"])
        print("   verification.search_parameters:", t_data["verification"].get("search_parameters"))
        print("   verification.candidate_within_corridor:", t_data["verification"].get("candidate_within_corridor"))
        print("   verification.closest_approach_ais_point ts:", t_data["verification"].get("closest_approach_ais_point", {}).get("timestamp"))
        print("   verification.closest_approach_distance_km:", t_data["verification"].get("closest_approach_distance_km"))
        print("   verification.timestamp_nearest_distance_from_origin_km:", t_data["verification"].get("timestamp_nearest_distance_from_origin_km"))

        assert t_data["attribution"]["candidate_count"] == 1
        assert t_data["attribution"]["top_vessel"] == "SYNTH-Y2019-000019"
        assert t_data["attribution"]["top_candidate_vessel_id"] == "SYNTH-Y2019-000019"
        assert t_data["attribution"]["top_score"] == 0.3007
        assert "attribution_qualification" in t_data["attribution"]

        search_params = t_data["verification"]["search_parameters"]
        assert search_params["drift_uncertainty_radius_km"] == 0.634
        assert search_params["candidate_search_corridor_radius_km"] == 30.0
        assert search_params["temporal_window_hours"] == 2.0
        assert t_data["verification"]["candidate_within_corridor"] is True
        assert t_data["verification"]["closest_approach_distance_km"] == 7.436

        t_vessels = t_data["vessels"]
        print(f"   real vessel: id={t_vessels[0]['vessel_id']}, rank={t_vessels[0]['rank']}, score={t_vessels[0]['score']}, correlation={t_vessels[0]['trajectory_correlation']}, is_mock_comparison={t_vessels[0].get('is_mock_comparison')}")
        assert t_vessels[0]["rank"] == 1
        assert t_vessels[0]["score"] == 0.3007
        assert t_vessels[0]["is_mock_comparison"] is False
        assert t_vessels[0]["trajectory_correlation"] == 0.33

        for i, mv in enumerate(t_vessels[1:], 1):
            print(f"   mock {i}: id={mv['vessel_id']}, rank={mv['rank']}, score={mv['score']}, correlation={mv['trajectory_correlation']}, is_mock_comparison={mv.get('is_mock_comparison')}")
            assert mv["rank"] is None
            assert mv["score"] is None
            assert mv["is_mock_comparison"] is True
            assert mv["trajectory_correlation"] is None

        # 4. POST /demo/spills/spill_75bc16/backtrack
        r_bt = await client.post("/api/v1/demo/spills/spill_75bc16/backtrack")
        assert r_bt.status_code == 200, r_bt.text
        bt_data = r_bt.json()
        print("\n4. POST /demo/spills/spill_75bc16/backtrack:")
        print("   attribution:", bt_data["attribution"])
        assert bt_data["attribution"]["candidate_count"] == 1
        assert bt_data["attribution"]["top_vessel"] == "SYNTH-Y2019-000019"
        assert bt_data["attribution"]["top_score"] == 0.3007

    print("\nALL COLD-START AND LIVE ATTRIBUTION PARITY CHECKS PASSED!")

if __name__ == "__main__":
    asyncio.run(main())
