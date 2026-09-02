from __future__ import annotations

import asyncio
from datetime import timezone

import pandas as pd
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.scoring_engine import ScoringEngine


SCENARIO_ID = "scenario-003"

SOURCE_VESSEL = "SYNTH-003-SRC"

DECOYS = [
    "SYNTH-003-DCY01",
    "SYNTH-003-DCY02",
    "SYNTH-003-DCY03",
    "SYNTH-003-DCY04",
    "SYNTH-003-DCY05",
]

VESSEL_IDS = [SOURCE_VESSEL] + DECOYS

SOURCE_LATITUDE = 35.05
SOURCE_LONGITUDE = 24.04

RELEASE_TIME = pd.Timestamp("2019-07-15 12:00:00")

WINDOW_START = RELEASE_TIME - pd.Timedelta(hours=2)
WINDOW_END = RELEASE_TIME + pd.Timedelta(hours=2)


async def load_trajectories() -> pd.DataFrame:

    print("\nQUERY WINDOW")
    print(f"Start: {WINDOW_START}")
    print(f"End  : {WINDOW_END}")
    print()

    start_time = WINDOW_START.to_pydatetime().replace(
        tzinfo=pd.Timestamp.utcnow().tz
    )
    end_time = WINDOW_END.to_pydatetime().replace(
        tzinfo=pd.Timestamp.utcnow().tz
    )

    async with AsyncSessionLocal() as db:

        result = await db.execute(
            text(
                """
                SELECT
                    vessel_id,
                    timestamp,
                    latitude,
                    longitude,
                    speed,
                    course,
                    heading
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                  AND is_synthetic = TRUE
                  AND vessel_id = ANY(:vessel_ids)
                  AND timestamp >= :start_time
                  AND timestamp <= :end_time
                ORDER BY vessel_id, timestamp
                """
            ),
            {
                "scenario_id": SCENARIO_ID,
                "vessel_ids": VESSEL_IDS,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        rows = result.mappings().all()

    print("=" * 80)
    print("DATABASE QUERY RESULT")
    print("=" * 80)

    print(f"Total rows: {len(rows)}")
    print()

    for vessel_id in VESSEL_IDS:

        vessel_rows = [
            row
            for row in rows
            if row["vessel_id"] == vessel_id
        ]

        print(
            f"{vessel_id}: "
            f"{len(vessel_rows)} rows"
        )

        if vessel_rows:
            print(
                f"    {vessel_rows[0]['timestamp']}"
                f" -> "
                f"{vessel_rows[-1]['timestamp']}"
            )

    print()

    if not rows:
        raise RuntimeError(
            "No AIS rows found for Scenario-003 "
            "in the 10:00-14:00 window."
        )

    df = pd.DataFrame(rows)

    df["timestamp"] = (
        pd.to_datetime(df["timestamp"], utc=True)
        .dt.tz_localize(None)
    )

    print("=" * 80)
    print("DATAFRAME RESULT")
    print("=" * 80)

    print(f"Rows   : {len(df)}")
    print(f"Vessels: {df['vessel_id'].nunique()}")
    print()

    print("Rows by vessel:")
    print(df.groupby("vessel_id").size())

    print()

    print("Time ranges:")
    print(
        df.groupby("vessel_id")["timestamp"]
        .agg(["min", "max"])
    )

    return df
async def main():

    print("=" * 80)
    print("SCENARIO-003 PURE AIS SCORING DIAGNOSTIC")
    print("=" * 80)

    print(f"Scenario       : {SCENARIO_ID}")
    print(f"Source vessel  : {SOURCE_VESSEL}")
    print(
        f"Source location: "
        f"{SOURCE_LATITUDE}, {SOURCE_LONGITUDE}"
    )
    print(f"Release time   : {RELEASE_TIME}")

    df = await load_trajectories()

    scoring_engine = ScoringEngine()

    results = []

    for vessel_id in VESSEL_IDS:

        result = scoring_engine.score_vessel(
            vessel_id=vessel_id,
            df=df,
            source_latitude=SOURCE_LATITUDE,
            source_longitude=SOURCE_LONGITUDE,
            estimated_release_time=RELEASE_TIME,
        )

        results.append(result)

    results.sort(
        key=lambda x: x.total_score,
        reverse=True,
    )

    print()
    print("=" * 80)
    print("RANKING")
    print("=" * 80)

    print(
        f"{'Rank':<6}"
        f"{'Vessel':<25}"
        f"{'Total':<10}"
        f"{'Proximity':<12}"
        f"{'Temporal':<11}"
        f"{'Slowdown':<11}"
        f"{'Loiter':<10}"
        f"{'Approach':<11}"
        f"{'Departure':<11}"
        f"{'Distance':<12}"
    )

    print("-" * 110)

    for rank, result in enumerate(results, start=1):

        print(
            f"{rank:<6}"
            f"{result.vessel_id:<25}"
            f"{result.total_score:<10.4f}"
            f"{result.proximity_score:<12.4f}"
            f"{result.temporal_score:<11.4f}"
            f"{result.slowdown_score:<11.4f}"
            f"{result.loiter_score:<10.4f}"
            f"{result.approach_score:<11.4f}"
            f"{result.departure_score:<11.4f}"
            f"{result.closest_distance_km:<12.4f}"
        )

    source_result = next(
        result
        for result in results
        if result.vessel_id == SOURCE_VESSEL
    )

    source_rank = (
        results.index(source_result) + 1
    )

    print()
    print("=" * 80)
    print("RESULT")
    print("=" * 80)

    print(
        f"Top prediction : "
        f"{results[0].vessel_id}"
    )

    print(
        f"Source vessel  : "
        f"{SOURCE_VESSEL}"
    )

    print(
        f"Source rank    : "
        f"{source_rank}"
    )

    print(
        f"Source score   : "
        f"{source_result.total_score:.4f}"
    )

    print(
        f"Top score      : "
        f"{results[0].total_score:.4f}"
    )

    if results[0].vessel_id == SOURCE_VESSEL:
        print()
        print("PASS: Source vessel ranked #1.")
    else:
        print()
        print("FAIL: Source vessel was NOT ranked #1.")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())