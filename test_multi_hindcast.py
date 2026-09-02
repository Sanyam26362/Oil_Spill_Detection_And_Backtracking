from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from datetime import datetime, timezone
import csv

CSV = "detections_for_env_test.csv"

rows = list(csv.DictReader(
    open(CSV, newline="", encoding="utf-8-sig")
))

w = WeatherService(
    weather_yearly_dir="data/weather/raw/yearly",
    ocean_yearly_dir="data/ocean/raw/yearly",
)

d = DriftEngine(weather_service=w)
h = HindcastService(drift_engine=d)

print("=" * 100)
print("MULTI-DETECTION HINDCAST TEST")
print("=" * 100)

# Test first detection from several different periods.
indices = [
    0,
    len(rows) // 4,
    len(rows) // 2,
    (3 * len(rows)) // 4,
    len(rows) - 1,
]

for index in indices:

    row = rows[index]

    timestamp = datetime.fromisoformat(
        row["detected_at"].replace("Z", "+00:00")
    )

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    print()
    print("-" * 100)
    print(f"TEST #{indices.index(index) + 1}")
    print("-" * 100)

    print("Detection:")
    print("  Latitude :", row["centroid_lat"])
    print("  Longitude:", row["centroid_lon"])
    print("  Time     :", timestamp)

    try:

        result = h.backward_ensemble(
            obs_latitude=float(row["centroid_lat"]),
            obs_longitude=float(row["centroid_lon"]),
            obs_time=timestamp,
            duration_hours=6,
            ensemble_size=100,
            initial_radius_m=500,
            timestep_minutes=15,
            random_seed=42,
        )

        print()
        print("Hindcast:")
        print("  Particles:", len(result.particles))
        print(
            "  Source centroid:",
            result.centroid_latitude,
            result.centroid_longitude,
        )
        print(
            "  Radius (km):",
            result.radius_km,
        )

        print()
        print("Status: PASS")

    except Exception as exc:

        print()
        print("Status: FAIL")
        print("Error:", repr(exc))

print()
print("=" * 100)
print("TEST COMPLETE")
print("=" * 100)

w.close()
