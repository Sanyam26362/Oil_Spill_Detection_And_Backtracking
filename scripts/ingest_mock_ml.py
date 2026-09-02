import requests
import json

MOCK_PAYLOAD = {
  "detections": [
    {
      "spill_id": "spill_79fd8a",
      "detected_at": "2019-01-01T03:42:35Z",
      "centroid": {
        "lon": 24.056,
        "lat": 35.0498
      },
      "polygon": [
        [24.0535, 35.0541],
        [24.0584, 35.0541],
        [24.0584, 35.0455],
        [24.0535, 35.0455],
        [24.0535, 35.0541]
      ],
      "area_km2": 0.43,
      "estimated_age_hours": 22.7,
      "confidence_score": 0.79,
      "cloudinary_url": "https://mock.cloudinary.com/demo/image/upload/spill_001.jpg"
    }
  ]
}

def ingest_mock():
    url = "http://localhost:8000/api/v1/spills/ingest-ml"
    response = requests.post(url, json=MOCK_PAYLOAD)
    if response.status_code == 201:
        print("Mock ML data successfully ingested into PostgreSQL.")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Failed: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    ingest_mock()