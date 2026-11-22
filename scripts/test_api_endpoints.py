import os
import sys
import socket
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Setup DNS workaround for Neon on local machines if necessary
orig_getaddrinfo = socket.getaddrinfo
def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if 'neon.tech' in host:
        return orig_getaddrinfo('3.147.219.177', port, family, type, proto, flags)
    return orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = custom_getaddrinfo

from fastapi.testclient import TestClient
from app.main import app

def test_endpoints():
    with TestClient(app) as client:
        print("Testing /health...")
        r = client.get("/health")
        print("Health status:", r.status_code, r.json())
        assert r.status_code == 200

        print("\nTesting /health/ready...")
        r = client.get("/health/ready")
        print("Health ready:", r.status_code, r.json())
        assert r.status_code == 200

        print("\nTesting GET /api/v1/demo/spills?page=1&page_size=5...")
        r = client.get("/api/v1/demo/spills?page=1&page_size=5")
        print("List spills status:", r.status_code)
        data = r.json()
        print("Total spills:", data.get("total"), "Page size:", len(data.get("items", [])))
        assert r.status_code == 200
        assert data.get("total") == 377
        first_spill_id = data["items"][0]["spill_id"]
        print("First spill ID:", first_spill_id)

        print(f"\nTesting GET /api/v1/demo/spills/{first_spill_id}...")
        r = client.get(f"/api/v1/demo/spills/{first_spill_id}")
        print("Detail status:", r.status_code, "Area:", r.json().get("area_km2"), "Top vessel:", r.json().get("ranked_top_vessel"))
        assert r.status_code == 200

        print(f"\nTesting GET /api/v1/demo/spills/{first_spill_id}/vessels...")
        r = client.get(f"/api/v1/demo/spills/{first_spill_id}/vessels")
        v_data = r.json()
        print("Vessels status:", r.status_code, "Count:", len(v_data.get("vessels", [])))
        assert r.status_code == 200
        assert len(v_data.get("vessels", [])) > 0

        print(f"\nTesting GET /api/v1/demo/spills/{first_spill_id}/attribution/trajectory...")
        r = client.get(f"/api/v1/demo/spills/{first_spill_id}/attribution/trajectory")
        attr_data = r.json()
        print("Attribution status:", r.status_code, "Spill ID:", attr_data.get("spill_id"))
        assert r.status_code == 200

        print(f"\nTesting GET /api/v1/visualization/spills/{first_spill_id}...")
        r = client.get(f"/api/v1/visualization/spills/{first_spill_id}")
        viz_data = r.json()
        print("Visualization status:", r.status_code, "Trajectory points:", len(viz_data.get("trajectory", [])))
        assert r.status_code == 200

        print(f"\nTesting GET /api/v1/demo/spills/{first_spill_id}/predict...")
        r = client.get(f"/api/v1/demo/spills/{first_spill_id}/predict")
        fc_data = r.json()
        print("Forecast status:", r.status_code, "Trajectory points:", len(fc_data.get("trajectory", [])))
        assert r.status_code == 200

        print(f"\nTesting POST /api/v1/demo/spills/{first_spill_id}/backtrack...")
        r = client.post(f"/api/v1/demo/spills/{first_spill_id}/backtrack")
        bt_data = r.json()
        print("Backtrack status:", r.status_code, "Attribution:", bt_data.get("attribution"))
        assert r.status_code == 200

        print(f"\nTesting GET /api/v1/drift/{first_spill_id}/diagnostic-plot...")
        r = client.get(f"/api/v1/drift/{first_spill_id}/diagnostic-plot")
        dp_data = r.json()
        print("Diagnostic plot status:", r.status_code, "URL:", dp_data.get("diagnostic_plot_url")[:40] if dp_data.get("diagnostic_plot_url") else None)
        assert r.status_code == 200

        print("\nALL 9 ENDPOINTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    test_endpoints()
