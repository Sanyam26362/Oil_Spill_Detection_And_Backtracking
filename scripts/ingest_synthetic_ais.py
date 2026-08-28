from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.core.database import AsyncSessionLocal


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = (
    PROJECT_ROOT
    / "data"
    / "ais"
    / "processed"
    / "synthetic_scenario_002.csv"
)


async def main() -> None:

    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Synthetic AIS CSV not found: {CSV_PATH}"
        )

    df = pd.read_csv(CSV_PATH)

    required_columns = {
        "vessel_id",
        "timestamp",
        "longitude",
        "latitude",
        "speed",
        "course",
        "heading",
        "vessel_type",
        "country",
        "is_synthetic",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    print()
    print("=" * 80)
    print("SYNTHETIC AIS INGESTION")
    print("=" * 80)

    print(
        f"CSV records  : {len(df):,}"
    )

    print(
        f"CSV vessels  : "
        f"{df['vessel_id'].nunique():,}"
    )

    async with AsyncSessionLocal() as session:

        # ----------------------------------------------------------
        # Safety check
        # ----------------------------------------------------------

        result = await session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ais_positions
                WHERE is_synthetic = TRUE
                """
            )
        )

        existing_synthetic = result.scalar_one()

        if existing_synthetic > 0:
            raise RuntimeError(
                "Synthetic AIS already exists in the database "
                f"({existing_synthetic:,} rows). "
                "Refusing to insert duplicates."
            )

        # ----------------------------------------------------------
        # Validate that this really is synthetic data.
        # ----------------------------------------------------------

        if not df["is_synthetic"].fillna(False).all():
            raise ValueError(
                "Input CSV contains non-synthetic records."
            )

        # ----------------------------------------------------------
        # Insert vessel metadata.
        # ----------------------------------------------------------

        vessels = (
            df[
                [
                    "vessel_id",
                    "country",
                    "vessel_type",
                ]
            ]
            .drop_duplicates(
                subset=["vessel_id"]
            )
        )

        print(
            f"Inserting vessels: {len(vessels):,}"
        )

        for row in vessels.itertuples(
            index=False
        ):

            await session.execute(
                text(
                    """
                    INSERT INTO vessels (
                        vessel_id,
                        country,
                        shiptype_name
                    )
                    VALUES (
                        :vessel_id,
                        :country,
                        :shiptype_name
                    )
                    ON CONFLICT (vessel_id)
                    DO UPDATE SET
                        country = EXCLUDED.country,
                        shiptype_name = EXCLUDED.shiptype_name
                    """
                ),
                {
                    "vessel_id": row.vessel_id,
                    "country": row.country,
                    "shiptype_name": row.vessel_type,
                },
            )

        # ----------------------------------------------------------
        # Insert AIS observations.
        # ----------------------------------------------------------

        print(
            f"Inserting AIS rows: {len(df):,}"
        )

        for row in df.itertuples(
            index=False
        ):

            await session.execute(
                text(
                    """
                    INSERT INTO ais_positions (
                        vessel_id,
                        timestamp,
                        longitude,
                        latitude,
                        speed,
                        course,
                        heading,
                        geometry,
                        is_synthetic
                    )
                    VALUES (
                        :vessel_id,
                        :timestamp,
                        :longitude,
                        :latitude,
                        :speed,
                        :course,
                        :heading,
                        ST_SetSRID(
                            ST_MakePoint(
                                :longitude,
                                :latitude
                            ),
                            4326
                        ),
                        TRUE
                    )
                    """
                ),
                {
                    "vessel_id": row.vessel_id,
                    "timestamp": row.timestamp.to_pydatetime(),
                    "longitude": float(row.longitude),
                    "latitude": float(row.latitude),
                    "speed": (
                        None
                        if pd.isna(row.speed)
                        else float(row.speed)
                    ),
                    "course": (
                        None
                        if pd.isna(row.course)
                        else float(row.course)
                    ),
                    "heading": (
                        None
                        if pd.isna(row.heading)
                        else float(row.heading)
                    ),
                },
            )

        await session.commit()

    print()
    print("=" * 80)
    print("INGESTION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())