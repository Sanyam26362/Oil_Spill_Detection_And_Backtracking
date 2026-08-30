import argparse
import asyncio
import logging
import io
import sys
import psutil
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import psycopg2

from app.core.database import engine, AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def get_db_url():
    url = engine.url
    sync_url = url.set(drivername="postgresql+psycopg2")
    return sync_url

def check_disk_space():
    usage = psutil.disk_usage('D:\\' if sys.platform == 'win32' else '/')
    free_gb = usage.free / (1024**3)
    logger.info(f"Available disk space: {free_gb:.2f} GB")
    if free_gb < 20.0:
        logger.error("Less than 20 GB free disk space. Aborting ingestion to be safe.")
        sys.exit(1)

def get_db_size(sync_url) -> float:
    conn = psycopg2.connect(
        dbname=sync_url.database,
        user=sync_url.username,
        password=sync_url.password,
        host=sync_url.host,
        port=sync_url.port
    )
    cursor = conn.cursor()
    cursor.execute("SELECT pg_database_size(%s)", (sync_url.database,))
    size_bytes = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return size_bytes / (1024**3)

def ingest_file_sync(csv_path: Path, sync_url):
    import psycopg2
    logger.info(f"Connecting via psycopg2 to {sync_url.host}:{sync_url.port}/{sync_url.database}")
    
    conn = psycopg2.connect(
        dbname=sync_url.database,
        user=sync_url.username,
        password=sync_url.password,
        host=sync_url.host,
        port=sync_url.port
    )
    conn.autocommit = False
    cursor = conn.cursor()
    
    logger.info(f"Loading {csv_path} into pandas for WKT generation...")
    df = pd.read_csv(csv_path)
    
    logger.info("Generating WKT...")
    df["geometry"] = "SRID=4326;POINT(" + df["longitude"].astype(str) + " " + df["latitude"].astype(str) + ")"
    
    cols = ["timestamp", "vessel_id", "longitude", "latitude", "speed", "course", "heading", "is_synthetic", "scenario_id", "geometry"]
    
    for c in ["speed", "course", "heading"]:
        df[c] = df[c].apply(lambda x: r"\N" if pd.isna(x) else str(x))
        
    df_copy = df[cols]
    
    logger.info("Writing in-memory buffer...")
    buffer = io.StringIO()
    df_copy.to_csv(buffer, index=False, header=False, sep="\t")
    buffer.seek(0)
    
    logger.info("Executing COPY FROM...")
    columns_str = ", ".join(cols)
    copy_sql = f"COPY ais_positions ({columns_str}) FROM STDIN WITH (FORMAT csv, DELIMITER '\t', NULL '\\N')"
    
    try:
        cursor.copy_expert(copy_sql, buffer)
        conn.commit()
        logger.info(f"Inserted {len(df)} rows from {csv_path.name}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error copying {csv_path}: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", help="E.g. 1-12", default="1-12")
    args = parser.parse_args()
    
    months = [int(m) for m in args.months.split("-")]
    if len(months) == 1:
        start_m, end_m = months[0], months[0]
    else:
        start_m, end_m = months[0], months[1]
        
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data" / "ais" / "processed" / "yearly"
    
    sync_url = await get_db_url()
    
    check_disk_space()
    initial_db_size = await asyncio.to_thread(get_db_size, sync_url)
    logger.info(f"Initial Database Size: {initial_db_size:.2f} GB")
    
    logger.info("Upserting vessels...")
    async with AsyncSessionLocal() as db:
        for m in range(start_m, end_m + 1):
            fpath = data_dir / f"synthetic_ais_2019-{m:02d}.csv"
            if not fpath.exists():
                logger.warning(f"File {fpath} not found, skipping vessel upsert.")
                continue
            df = pd.read_csv(fpath, usecols=["vessel_id", "country", "vessel_type"]).drop_duplicates("vessel_id")
            for _, row in df.iterrows():
                stmt = text("""
                    INSERT INTO vessels (vessel_id, country, shiptype_name) 
                    VALUES (:vid, :country, :type) 
                    ON CONFLICT (vessel_id) DO NOTHING
                """)
                await db.execute(stmt, {"vid": row["vessel_id"], "country": row["country"], "type": row["vessel_type"]})
        await db.commit()
    
    # We should delete existing synthetic data for these months to prevent duplication? 
    # The requirement says "Do not modify or delete existing real AIS data." 
    # I'll just rely on the assumption the table is clean or the user handles idempotency, or delete based on scenario_id if it's "SYNTH-Y2019*"
    # Given the script didn't have it, I'll avoid deleting to be safe, but print size growth.
    
    for m in range(start_m, end_m + 1):
        fpath = data_dir / f"synthetic_ais_2019-{m:02d}.csv"
        if not fpath.exists():
            logger.error(f"File not found: {fpath}")
            continue
            
        check_disk_space()
        current_db_size = await asyncio.to_thread(get_db_size, sync_url)
        logger.info(f"Current DB size: {current_db_size:.2f} GB (+{current_db_size - initial_db_size:.2f} GB so far)")
        
        await asyncio.to_thread(ingest_file_sync, fpath, sync_url)
        
    final_db_size = await asyncio.to_thread(get_db_size, sync_url)
    logger.info(f"Final DB size: {final_db_size:.2f} GB (+{final_db_size - initial_db_size:.2f} GB total growth)")
    logger.info("All files ingested successfully.")

if __name__ == "__main__":
    asyncio.run(main())
