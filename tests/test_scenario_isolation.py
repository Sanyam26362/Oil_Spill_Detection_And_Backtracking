import pytest
from datetime import datetime, timezone
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.repositories.ais_repository import AISRepository
from app.services.attribution_engine import AttributionEngine
from scripts.benchmark.runner import ingest_scenario
from app.services.weather_service import WeatherService


@pytest.mark.asyncio
async def test_scenario_isolation_in_repository():
    """
    Test that AISRepository.get_candidate_vessels respects scenario_id,
    even when multiple synthetic scenarios overlap in space and time.
    """
    repo = AISRepository()

    # Create overlapping scenarios
    # Scenario A
    df_a = pd.DataFrame([
        {
            "vessel_id": "SYNTH-A-01",
            "timestamp": "2020-01-01T12:00:00Z",
            "longitude": 30.0,
            "latitude": 30.0,
            "speed": 10.0,
            "course": 90.0,
            "heading": 90.0,
            "is_synthetic": True,
            "scenario_id": "SCENARIO-A",
        }
    ])
    # Scenario B
    df_b = pd.DataFrame([
        {
            "vessel_id": "SYNTH-B-01",
            "timestamp": "2020-01-01T12:00:00Z",
            "longitude": 30.0,
            "latitude": 30.0,
            "speed": 10.0,
            "course": 90.0,
            "heading": 90.0,
            "is_synthetic": True,
            "scenario_id": "SCENARIO-B",
        }
    ])

    await ingest_scenario(df_a, "SCENARIO-A")
    await ingest_scenario(df_b, "SCENARIO-B")

    start_time = datetime(2020, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2020, 1, 1, 14, 0, 0, tzinfo=timezone.utc)

    async with AsyncSessionLocal() as db:
        # Query Scenario A
        candidates_a = await repo.get_candidate_vessels(
            db=db,
            latitude=30.0,
            longitude=30.0,
            radius_km=10.0,
            start_time=start_time,
            end_time=end_time,
            synthetic_only=True,
            scenario_id="SCENARIO-A"
        )
        assert "SYNTH-A-01" in candidates_a
        assert "SYNTH-B-01" not in candidates_a

        # Query Scenario B
        candidates_b = await repo.get_candidate_vessels(
            db=db,
            latitude=30.0,
            longitude=30.0,
            radius_km=10.0,
            start_time=start_time,
            end_time=end_time,
            synthetic_only=True,
            scenario_id="SCENARIO-B"
        )
        assert "SYNTH-B-01" in candidates_b
        assert "SYNTH-A-01" not in candidates_b
