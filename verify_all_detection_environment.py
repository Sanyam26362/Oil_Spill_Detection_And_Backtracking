import csv
import numpy as np
from datetime import datetime, timezone
from app.services.weather_service import WeatherService

CSV = "detections_for_env_test.csv"

rows = list(csv.DictReader(open(CSV, newline="", encoding="utf-8-sig")))

print("=" * 100)
print("EXHAUSTIVE ENVIRONMENTAL LOOKUP TEST")
print("=" * 100)
print(f"TOTAL DETECTIONS: {len(rows)}")
print()

service = WeatherService(
    weather_yearly_dir="data/weather/raw/yearly",
    ocean_yearly_dir="data/ocean/raw/yearly",
)

passed = 0
failed = 0
errors = []

for index, row in enumerate(rows, start=1):

    try:
        timestamp = datetime.fromisoformat(
            row["detected_at"].replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        result = service.get_velocity(
            latitude=float(row["centroid_lat"]),
            longitude=float(row["centroid_lon"]),
            timestamp=timestamp,
        )

        values = [
            result.wind_u,
            result.wind_v,
            result.current_u,
            result.current_v,
        ]

        if all(np.isfinite(values)):
            passed += 1
        else:
            failed += 1
            errors.append({
                "row": index,
                "lat": row["centroid_lat"],
                "lon": row["centroid_lon"],
                "time": row["detected_at"],
                "result": result,
                "reason": "NON-FINITE VALUE",
            })

    except Exception as exc:
        failed += 1
        errors.append({
            "row": index,
            "lat": row["centroid_lat"],
            "lon": row["centroid_lon"],
            "time": row["detected_at"],
            "result": None,
            "reason": repr(exc),
        })

    if index % 100 == 0:
        print(f"Processed: {index}/{len(rows)}")

service.close()

print()
print("=" * 100)
print("FINAL RESULT")
print("=" * 100)

print(f"TOTAL : {len(rows)}")
print(f"PASS  : {passed}")
print(f"FAIL  : {failed}")

if rows:
    print(f"RATE  : {passed / len(rows) * 100:.2f}%")

print()

if failed == 0:
    print("? ALL DETECTIONS RETURN FINITE ENVIRONMENTAL VALUES")
    print("? WEATHER LOOKUPS: PASS")
    print("? CURRENT LOOKUPS: PASS")
    print("? EXHAUSTIVE DETECTION TEST: PASS")
else:
    print("? SOME DETECTIONS FAILED")
    print()
    print("FIRST 10 FAILURES:")
    for error in errors[:10]:
        print(error)

print("=" * 100)

