import pytest
import asyncio
from datetime import timedelta, datetime, timezone
import xarray as xr
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.spill import OilSpillDetection
from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine

@pytest.fixture(scope="module")
def detections():
    import asyncio
    from app.core.database import AsyncSessionLocal, engine
    from app.models.spill import OilSpillDetection
    from sqlalchemy import select
    
    async def fetch_detections():
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(OilSpillDetection))
            items = result.scalars().all()
        await engine.dispose()
        return items
        
    loop = asyncio.new_event_loop()
    try:
        items = loop.run_until_complete(fetch_detections())
    finally:
        loop.close()
    return items

def get_estimated_release_time(detection: OilSpillDetection) -> datetime:
    from datetime import timedelta, timezone
    # Ensure timezone is UTC naive for WeatherService
    dt = detection.detected_at - timedelta(hours=detection.estimated_age_hours)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def test_detection_coverage_stats(detections):
    total_detections = len(detections)

    # 35.5N, 23.5W, 34.5S, 24.5E
    lat_min, lat_max = 34.5, 35.5
    lon_min, lon_max = 23.5, 24.5

    inside_spatial = 0
    outside_spatial = 0
    require_2018 = 0
    processable = 0

    release_times = []

    for d in detections:
        rt = get_estimated_release_time(d)
        release_times.append(rt)

        if rt.year < 2019:
            require_2018 += 1
            continue

        if lat_min <= d.centroid_lat <= lat_max and lon_min <= d.centroid_lon <= lon_max:
            inside_spatial += 1
            processable += 1
        else:
            outside_spatial += 1

    earliest = min(release_times)
    latest = max(release_times)

    print("\n=== Detection Coverage Stats ===")
    print(f"Total detections: {total_detections}")
    print(f"Inside available spatial data: {inside_spatial}")
    print(f"Outside spatial coverage: {outside_spatial}")
    print(f"Requiring 2018 data: {require_2018}")
    print(f"Earliest release time: {earliest}")
    print(f"Latest release time: {latest}")
    print("================================\n")

    assert total_detections > 0
    assert inside_spatial > 0

@pytest.fixture(scope="module")
def weather_service():
    ws = WeatherService(
        weather_yearly_dir="data/weather/raw/yearly",
        ocean_yearly_dir="data/ocean/raw/yearly"
    )
    yield ws
    ws.close()

def test_weather_service_actual_detections(detections, weather_service):
    # Test at least several detections from different months across 2019.
    # Group detections by month
    by_month = {}
    for d in detections:
        rt = get_estimated_release_time(d)
        if rt.year == 2019:
            by_month.setdefault(rt.month, []).append((d, rt))

    # Sample 1 detection from each month
    samples = []
    for month, dets in by_month.items():
        if dets:
            samples.append(dets[0])

    assert len(samples) > 0, "No 2019 detections found"

    print(f"\nTesting {len(samples)} actual detections across different months.")

    for d, rt in samples:
        print(f"Testing detection {d.id} at {rt} (Lat: {d.centroid_lat}, Lon: {d.centroid_lon})")
        try:
            vel = weather_service.get_velocity(d.centroid_lat, d.centroid_lon, rt)
            assert vel.wind_u == vel.wind_u, "wind_u is NaN"
            assert vel.wind_v == vel.wind_v, "wind_v is NaN"
            assert vel.current_u == vel.current_u, "current_u is NaN"
            assert vel.current_v == vel.current_v, "current_v is NaN"
            print(f"  -> SUCCESS: wind=({vel.wind_u:.2f}, {vel.wind_v:.2f}), current=({vel.current_u:.2f}, {vel.current_v:.2f})")
        except Exception as e:
            pytest.fail(f"Failed to lookup velocity for detection {d.id}: {e}")

def test_drift_engine_actual_detection(detections, weather_service):
    # Take the first valid 2019 detection
    valid = None
    for d in detections:
        rt = get_estimated_release_time(d)
        if rt.year == 2019:
            valid = (d, rt)
            break

    assert valid is not None
    d, rt = valid

    engine = DriftEngine(weather_service=weather_service, windage=0.03)

    print(f"\nTesting DriftEngine for detection {d.id} at {rt}")

    try:
        traj = engine.backward_drift(d.centroid_lat, d.centroid_lon, rt, duration_hours=2)
        assert len(traj.states) > 1

        # Verify timestamps are decreasing
        for i in range(1, len(traj.states)):
            assert traj.states[i].timestamp < traj.states[i-1].timestamp
            assert traj.states[i].wind_u == traj.states[i].wind_u

        print("  -> Backward Drift SUCCESS")
    except Exception as e:
        pytest.fail(f"Backward drift failed: {e}")

    try:
        trajs = engine.backward_drift_ensemble([d.centroid_lat], [d.centroid_lon], rt, duration_hours=2)
        assert len(trajs) == 1
        assert len(trajs[0].states) > 1
        print("  -> Ensemble Backward Drift SUCCESS")
    except Exception as e:
        pytest.fail(f"Ensemble backward drift failed: {e}")
