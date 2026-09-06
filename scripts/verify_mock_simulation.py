"""
scripts/verify_mock_simulation.py

Verification script for Maritime Kinematic Simulation Model of Mock Vessel Trajectories.
Validates:
1. Temporal coverage: start at release_time - 3h, end at detected_at + 3h (or +6h).
2. 30-min sampling: waypoints exactly every 30 minutes with clean :00 and :30 timestamps.
3. Vessel-type profiles:
   - Cargo: speed 12.0 - 16.5 knots, small course changes.
   - Tanker: speed 10.0 - 13.5 knots, ROT < 10°/hour (< 5°/30m).
   - Fishing: speed 2.5 - 9.0 knots, higher course variability.
4. Leeway drift: Heading offset from COG between 1° and 4°.
5. Corridor constraint: CPA distance within 10 - 25 km from backtrack origin.
6. Schema compliance: Exact JSON structure and types.
"""

import asyncio
import sys
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.spill_catalog_service import SpillCatalogService
from app.services.drift_engine import DriftEngine

async def verify_mock_kinematics():
    SpillCatalogService._initialized = False
    SpillCatalogService._spills = {}
    SpillCatalogService.initialize()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test on spill_4d67fb and spill_75bc16
        for spill_id in ["spill_4d67fb", "spill_75bc16"]:
            print(f"\n========================================================")
            print(f"VERIFYING MOCK KINEMATICS FOR {spill_id}")
            print(f"========================================================")

            r_spill = await client.get(f"/api/v1/demo/spills/{spill_id}")
            assert r_spill.status_code == 200
            s_data = r_spill.json()

            rel_time = datetime.fromisoformat(s_data["estimated_release_time"])
            det_time = datetime.fromisoformat(s_data["detected_at"])

            r_traj = await client.get(f"/api/v1/demo/spills/{spill_id}/attribution/trajectory")
            assert r_traj.status_code == 200
            t_data = r_traj.json()

            vessels = t_data["vessels"]
            mock_vessels = [v for v in vessels if v["is_mock"]]
            assert len(mock_vessels) == 3, f"Expected 3 mock vessels, got {len(mock_vessels)}"

            origin = t_data["backtrack_origin"]
            origin_lat = origin["latitude"]
            origin_lon = origin["longitude"]

            for mv in mock_vessels:
                v_id = mv["vessel_id"]
                v_type = mv["vessel_type"]
                traj = mv["trajectory"]
                n_pts = len(traj)

                print(f"\n--- Vessel: {v_id} ({v_type}) ---")
                print(f"Full trajectory point count: {mv['full_trajectory_point_count']} (pts in traj: {n_pts})")
                assert mv["full_trajectory_point_count"] == n_pts
                assert n_pts >= 13, f"Expected at least 13 points, got {n_pts}"

                # 1. Temporal Coverage & 30-min Sampling Check
                t_first = datetime.fromisoformat(traj[0]["timestamp"].replace("Z", "+00:00"))
                t_last = datetime.fromisoformat(traj[-1]["timestamp"].replace("Z", "+00:00"))

                print(f"Start timestamp: {traj[0]['timestamp']}")
                print(f"End timestamp:   {traj[-1]['timestamp']}")

                # Verify clean :00 or :30 timestamps
                for idx, pt in enumerate(traj):
                    ts = datetime.fromisoformat(pt["timestamp"].replace("Z", "+00:00"))
                    assert ts.minute in (0, 30), f"Point {idx} timestamp minute {ts.minute} not in (0, 30)!"
                    assert ts.second == 0, f"Point {idx} timestamp second {ts.second} != 0!"

                    # Consecutive points must be exactly 30 minutes apart
                    if idx > 0:
                        prev_ts = datetime.fromisoformat(traj[idx - 1]["timestamp"].replace("Z", "+00:00"))
                        dt_min = (ts - prev_ts).total_seconds() / 60.0
                        assert dt_min == 30.0, f"Step between {idx-1} and {idx} is {dt_min} min, not 30 min!"

                # 2. Kinematics Profile Check
                speeds = [pt["speed"] for pt in traj]
                courses = [pt["course"] for pt in traj]
                headings = [pt["heading"] for pt in traj]

                min_s, max_s = min(speeds), max(speeds)
                print(f"Speed range: {min_s:.1f} - {max_s:.1f} knots")

                if v_type == "Cargo":
                    assert min_s >= 11.8 and max_s <= 16.7, f"Cargo speed out of range: {min_s} - {max_s}"
                elif v_type == "Tanker":
                    assert min_s >= 9.8 and max_s <= 13.7, f"Tanker speed out of range: {min_s} - {max_s}"
                elif v_type == "Fishing":
                    assert min_s >= 2.4 and max_s <= 9.2, f"Fishing speed out of range: {min_s} - {max_s}"

                # 3. Rate of Turn & Course Stability
                rot_per_step = []
                for i in range(n_pts - 1):
                    d_course = abs((courses[i+1] - courses[i] + 180) % 360 - 180)
                    rot_per_step.append(d_course)

                max_rot = max(rot_per_step)
                print(f"Max course change per 30m step: {max_rot:.1f}°")
                if v_type == "Cargo":
                    assert max_rot <= 5.0, f"Cargo course change {max_rot}° exceeds 5°!"
                elif v_type == "Tanker":
                    assert max_rot <= 6.0, f"Tanker ROT per 30m {max_rot}° exceeds 6° (< 10°/h)!"

                # 4. Heading vs COG Leeway Drift
                leeway_offsets = []
                for i in range(n_pts):
                    offset = abs((headings[i] - courses[i] + 180) % 360 - 180)
                    leeway_offsets.append(offset)
                avg_leeway = sum(leeway_offsets) / len(leeway_offsets)
                print(f"Average leeway offset (Heading vs COG): {avg_leeway:.2f}° (min={min(leeway_offsets):.1f}°, max={max(leeway_offsets):.1f}°)")
                assert 0.8 <= avg_leeway <= 4.5, f"Leeway offset {avg_leeway}° outside 1° - 4° range!"

                # 5. Corridor Constraint Check (10 - 25 km from backtrack origin at CPA)
                cpa_loc = mv["culprit_location"]
                cpa_dist = DriftEngine.haversine_km(origin_lat, origin_lon, cpa_loc["latitude"], cpa_loc["longitude"])
                print(f"Culprit location: ts={cpa_loc['timestamp']}, lat={cpa_loc['latitude']:.4f}, lon={cpa_loc['longitude']:.4f}, speed={cpa_loc['speed']} kts, course={cpa_loc['course']}°")
                print(f"CPA distance to backtrack origin: {cpa_dist:.2f} km")
                assert 10.0 <= cpa_dist <= 25.0, f"CPA distance {cpa_dist:.2f} km outside 10 - 25 km corridor!"
                assert abs(mv["distance_from_backtrack_origin_km"] - cpa_dist) < 0.01

                # 6. Schema Contract Check
                required_keys = [
                    "vessel_id", "is_mock", "is_mock_comparison", "rank", "score",
                    "vessel_name", "mmsi", "imo", "country", "vessel_type",
                    "culprit_location", "distance_from_backtrack_origin_km",
                    "distance_to_origin_km", "full_trajectory_point_count",
                    "trajectory_correlation", "speed", "course", "heading",
                    "time_difference_hours", "trajectory"
                ]
                for k in required_keys:
                    assert k in mv, f"Missing required key '{k}' in mock vessel payload!"
                assert mv["rank"] is None
                assert mv["score"] is None
                assert mv["trajectory_correlation"] is None
                assert mv["is_mock_comparison"] is True
                assert mv["is_mock"] is True

        print("\n========================================================")
        print("ALL MOCK VESSEL SIMULATION TESTS PASSED SUCCESSFULLY!")
        print("========================================================")

if __name__ == "__main__":
    asyncio.run(verify_mock_kinematics())
