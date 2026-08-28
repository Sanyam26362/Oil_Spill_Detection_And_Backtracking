import argparse
import asyncio
import json
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, insert, select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.elements import WKTElement

from app.core.database import AsyncSessionLocal
from app.models.ais import AISPosition, Vessel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def ingest_scenario(csv_path: str, ground_truth_path: str | None = None) -> None:
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_file}")
        return

    logger.info(f"Loading data from {csv_file}")
    df = pd.read_csv(csv_file)

    required_cols = [
        "vessel_id", "timestamp", "longitude", "latitude",
        "speed", "course", "heading", "vessel_type",
        "country", "is_synthetic", "scenario_id"
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    if not df["is_synthetic"].all():
        raise ValueError("Not all rows are marked as synthetic (is_synthetic != True)")

    scenario_ids = df["scenario_id"].unique()
    if len(scenario_ids) != 1:
        raise ValueError(f"Multiple scenario IDs found in CSV: {scenario_ids}")
    
    scenario_id = str(scenario_ids[0])
    logger.info(f"Processing scenario: {scenario_id}")

    # Convert timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    
    # Process vessels
    vessels_df = df[["vessel_id", "country", "vessel_type"]].drop_duplicates("vessel_id")
    vessels = [
        {
            "vessel_id": row["vessel_id"],
            "country": row["country"],
            "shiptype_name": row["vessel_type"],
            "shiptype": None,
        }
        for _, row in vessels_df.iterrows()
    ]

    async with AsyncSessionLocal() as db:
        # Upsert vessels
        for chunk in [vessels[i:i + 1000] for i in range(0, len(vessels), 1000)]:
            stmt = pg_insert(Vessel).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["vessel_id"],
                set_={"country": stmt.excluded.country, "shiptype_name": stmt.excluded.shiptype_name}
            )
            await db.execute(stmt)
        
        # Delete existing data for this scenario to be idempotent
        logger.info("Cleaning up existing data for this scenario...")
        await db.execute(delete(AISPosition).where(AISPosition.scenario_id == scenario_id))
        await db.commit()

        # Prepare positions
        positions = []
        for _, row in df.iterrows():
            positions.append({
                "vessel_id": row["vessel_id"],
                "timestamp": row["timestamp"].to_pydatetime(),
                "longitude": float(row["longitude"]),
                "latitude": float(row["latitude"]),
                "speed": float(row["speed"]) if pd.notnull(row["speed"]) else None,
                "course": float(row["course"]) if pd.notnull(row["course"]) else None,
                "heading": float(row["heading"]) if pd.notnull(row["heading"]) else None,
                "geometry": WKTElement(f"SRID=4326;POINT({row['longitude']} {row['latitude']})", srid=4326),
                "is_synthetic": True,
                "scenario_id": scenario_id
            })

        logger.info(f"Inserting {len(positions)} AIS records...")
        
        # Insert in chunks of 1000 to avoid parameter limits
        chunk_size = 1000
        for i in range(0, len(positions), chunk_size):
            chunk = positions[i:i + chunk_size]
            await db.execute(insert(AISPosition).values(chunk))
        
        await db.commit()
        
        # Validation
        cnt = await db.scalar(select(func.count()).select_from(AISPosition).where(AISPosition.scenario_id == scenario_id))
        logger.info(f"Inserted row count: {cnt} (Expected: {len(positions)})")
        assert cnt == len(positions), "Row counts do not match!"
        
        if ground_truth_path:
            gt_file = Path(ground_truth_path)
            if gt_file.exists():
                with gt_file.open() as f:
                    gt = json.load(f)
                
                source_vid = gt["source"]["vessel_id"]
                source_ts = pd.to_datetime(gt["source"]["timestamp"]).to_pydatetime()
                
                # check release record
                src_stmt = select(AISPosition).where(
                    AISPosition.scenario_id == scenario_id,
                    AISPosition.vessel_id == source_vid,
                    AISPosition.timestamp == source_ts
                )
                res = await db.execute(src_stmt)
                rel_rec = res.scalars().first()
                if rel_rec:
                    logger.info("Validation passed: Source-vessel release record exists in DB.")
                else:
                    logger.error("Validation failed: Source-vessel release record missing!")
                    raise ValueError("Release record missing")

        logger.info("Ingestion complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to synthetic scenario CSV")
    parser.add_argument("--ground-truth", required=False, help="Path to ground truth JSON (optional)")
    args = parser.parse_args()
    
    asyncio.run(ingest_scenario(args.csv, args.ground_truth))
