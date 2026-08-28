from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pandas as pd

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import (
    AttributionEngine,
)
from app.services.weather_service import WeatherService


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OBSERVATION_PATH = (
    PROJECT_ROOT
    / "data/ais/processed/"
    "synthetic_scenario_002_observation.json"
)

ERA5_PATH = (
    PROJECT_ROOT
    / "data/weather/raw/"
    "era5_wind_2019-07-event.nc"
)

CMEMS_PATH = (
    PROJECT_ROOT
    / "data/ocean/raw/"
    "med_currents_2019-07-event.nc"
)


async def main() -> None:

    with OBSERVATION_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:
        payload = json.load(f)

    observation = payload["observation"]

    observation_time = (
        pd.Timestamp(
            observation["timestamp"]
        )
        .to_pydatetime()
    )

    with WeatherService(
        era5_path=ERA5_PATH,
        cmems_path=CMEMS_PATH,
    ) as weather:

        engine = AttributionEngine(
            weather_service=weather,
        )

        async with AsyncSessionLocal() as db:

            result = await engine.attribute(
                db=db,
                observation_latitude=(
                    observation["latitude"]
                ),
                observation_longitude=(
                    observation["longitude"]
                ),
                observation_time=observation_time,
                drift_duration_hours=6,
                ensemble_size=100,
                initial_radius_m=500,
                timestep_minutes=15,
                candidate_radius_margin_km=5,
                candidate_time_window_hours=2,
                synthetic_only=True,
            )

    print()
    print("=" * 90)
    print("END-TO-END POSTGIS ATTRIBUTION")
    print("=" * 90)

    source = result["source_estimate"]

    print(
        f"Estimated source: "
        f"{source['latitude']:.6f}, "
        f"{source['longitude']:.6f}"
    )

    print(
        f"Source radius: "
        f"{source['radius_km']:.3f} km"
    )

    print(
        f"Candidates: "
        f"{result['candidate_count']}"
    )

    print()

    if result["candidates"]:

        output = pd.DataFrame(
            result["candidates"]
        )

        print(
            output.to_string(
                index=False
            )
        )

        print()

        print(
            f"TOP PREDICTION: "
            f"{result['top_prediction']}"
        )

    else:
        print(
            "No candidate vessels found."
        )


if __name__ == "__main__":
    asyncio.run(main())