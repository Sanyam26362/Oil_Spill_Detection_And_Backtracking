from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    print("Health Status Code:", response.status_code)
    print("Health Response:", response.json())

if __name__ == "__main__":
    test_health()
