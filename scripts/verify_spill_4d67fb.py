import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.spill_catalog_service import SpillCatalogService
from app.repositories.ais_repository import AISRepository

async def main():
    # Force cold-boot catalog reload
    SpillCatalogService._initialized = False
    SpillCatalogService._spills = {}
    SpillCatalogService.initialize()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/v1/demo/spills/spill_4d67fb (Cold start)
        r_get = await client.get("/api/v1/demo/spills/spill_4d67fb")
        assert r_get.status_code == 200, r_get.text
        d_get = r_get.json()
        print("=== 1. GET /demo/spills/spill_4d67fb ===")
        print(f"candidate_count: {d_get.get('candidate_count')}")
        print(f"ranked_top_vessel: {d_get.get('ranked_top_vessel')}")
        print(f"ranked_top_score: {d_get.get('ranked_top_score')}")
        print(f"estimated_source_latitude: {d_get.get('estimated_source_latitude')}")
        print(f"estimated_source_longitude: {d_get.get('estimated_source_longitude')}")
        print(f"estimated_source_radius_km: {d_get.get('estimated_source_radius_km')}")

        assert d_get["candidate_count"] == 1
        assert d_get["ranked_top_vessel"] == "SYNTH-Y2019-000152"
        assert d_get["ranked_top_score"] == 0.2693

        # 2. POST /api/v1/demo/spills/spill_4d67fb/backtrack (Live engine)
        r_post = await client.post("/api/v1/demo/spills/spill_4d67fb/backtrack")
        assert r_post.status_code == 200, r_post.text
        d_post = r_post.json()
        print("\n=== 2. POST /demo/spills/spill_4d67fb/backtrack ===")
        print(f"candidate_count: {d_post['attribution']['candidate_count']}")
        print(f"top_vessel: {d_post['attribution']['top_vessel']}")
        print(f"top_score: {d_post['attribution']['top_score']}")
        source_est = d_post["backtrack"]["source_estimate"]
        print(f"source_estimate: {source_est}")

        assert d_post["attribution"]["candidate_count"] == 1
        assert d_post["attribution"]["top_vessel"] == "SYNTH-Y2019-000152"
        assert d_post["attribution"]["top_score"] == 0.2693

        # Parity check between catalog and backtrack
        assert round(d_get["estimated_source_latitude"], 5) == round(source_est["latitude"], 5)
        assert round(d_get["estimated_source_longitude"], 5) == round(source_est["longitude"], 5)
        print("\n--> Source centroid parity confirmed!")

        # 3. GET /api/v1/demo/spills/spill_4d67fb/attribution/trajectory
        r_traj = await client.get("/api/v1/demo/spills/spill_4d67fb/attribution/trajectory")
        assert r_traj.status_code == 200, r_traj.text
        d_traj = r_traj.json()
        real_vessel = d_traj["vessels"][0]
        pts = real_vessel["trajectory"]
        print("\n=== 3. GET /demo/spills/spill_4d67fb/attribution/trajectory ===")
        print(f"top_vessel: {d_traj['attribution']['top_vessel']}")
        print(f"top_score: {d_traj['attribution']['top_score']}")
        print(f"trajectory_correlation: {real_vessel.get('trajectory_correlation')}")
        print(f"Number of points: {len(pts)}")
        for idx, pt in enumerate(pts):
            print(f"  Point {idx}: {pt['timestamp']} | lat={pt['latitude']:.6f}, lon={pt['longitude']:.6f}")

        # Point 0 longitude must be within Crete corridor (23.0 to 24.5), NOT 31.019 (Cyprus)
        assert 23.0 <= pts[0]["longitude"] <= 24.5, f"Point 0 lon {pts[0]['longitude']} outside Crete corridor!"
        print("\n--> Point 0 is within Crete corridor (~23E - 24.5E), Cyprus spike eliminated!")

        # Speed between consecutive points <= 18 m/s
        from datetime import datetime
        max_speed = 0.0
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            t1 = datetime.fromisoformat(p1["timestamp"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(p2["timestamp"].replace("Z", "+00:00"))
            dt = (t2 - t1).total_seconds()
            dist = AISRepository._haversine_distance_m(p1["latitude"], p1["longitude"], p2["latitude"], p2["longitude"])
            speed = dist / dt if dt > 0 else 0
            if speed > max_speed:
                max_speed = speed
            print(f"  Leg {i}->{i+1}: dt={dt}s, dist={dist:.1f}m, speed={speed:.2f} m/s ({speed * 1.94384:.2f} kts)")
            assert speed <= 18.0, f"Speed {speed:.2f} m/s exceeded 18 m/s!"

        print(f"--> Max consecutive speed: {max_speed:.2f} m/s (<= 18.0 m/s confirmed)")

        # Verify dynamic correlation for 0.2693 evaluates to 0.30
        assert real_vessel["trajectory_correlation"] == 0.30, f"Expected 0.30, got {real_vessel['trajectory_correlation']}"
        print("--> Dynamic trajectory correlation 0.30 confirmed for score 0.2693!")

    print("\nALL VERIFICATIONS FOR SPILL_4D67FB PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
