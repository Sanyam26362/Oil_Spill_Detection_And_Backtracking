from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from app.core.database import AsyncSessionLocal
from app.repositories.ais_repository import AISRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OBSERVATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "ais"
    / "processed"
    / "synthetic_scenario_002_observation.json"
)


async def main() -> None:

    with OBSERVATION_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:
        payload = json.load(f)

    observation = payload["observation"]
    scenario_id = payload.get("scenario_id", "scenario-002")

    observation_time = pd.Timestamp(
        observation["timestamp"]
    )

    # For Scenario 002 the oil drifted for 6 hours.
    estimated_release_time = (
        observation_time
        - pd.Timedelta(hours=6)
    )

    # Our hindcast currently gave approximately a 0.535 km
    # source radius. Give PostGIS a modest search margin.
    estimated_source_lat = 33.500322
    estimated_source_lon = 34.001828
    search_radius_km = 5.535

    start_time = (
        estimated_release_time
        - pd.Timedelta(hours=2)
    )

    end_time = (
        estimated_release_time
        + pd.Timedelta(hours=2)
    )

    repository = AISRepository()

    async with AsyncSessionLocal() as db:

        candidates = await (
            repository.get_candidate_vessels(
                db=db,
                latitude=estimated_source_lat,
                longitude=estimated_source_lon,
                radius_km=search_radius_km,
                start_time=start_time.to_pydatetime(),
                end_time=end_time.to_pydatetime(),
                synthetic_only=True,
                scenario_id=scenario_id,
            )
        )

    print()
    print("=" * 80)
    print("POSTGIS AIS CANDIDATE EXTRACTION")
    print("=" * 80)

    print(
        f"Estimated source : "
        f"{estimated_source_lat:.6f}, "
        f"{estimated_source_lon:.6f}"
    )

    print(
        f"Search radius    : "
        f"{search_radius_km:.3f} km"
    )

    print(
        f"Time window      : "
        f"{start_time} → {end_time}"
    )

    print()

    print(
        f"Candidates found : "
        f"{len(candidates)}"
    )

    print()

    for vessel_id in candidates:
        print(vessel_id)

    print()

    if "SYNTH-000011" in candidates:
        print(
            "✅ SOURCE VESSEL FOUND "
            "BY POSTGIS"
        )
    else:
        print(
            "❌ SOURCE VESSEL NOT FOUND"
        )


if __name__ == "__main__":
    asyncio.run(main())