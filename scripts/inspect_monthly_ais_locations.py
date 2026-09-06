import asyncio
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from app.core.config import settings
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(raw_url)
    DB_CONFIG = {
        "user": parsed.username or "sih_admin",
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
    }
except Exception:
    DB_CONFIG = {
        "user": os.getenv("POSTGRES_USER", "sih_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "sih_secure_password_2026"),
        "database": os.getenv("POSTGRES_DB", "oil_spill_db"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
    }

MONTHS_2019 = [
    ("2019-01", datetime(2019, 1, 1, tzinfo=timezone.utc), datetime(2019, 2, 1, tzinfo=timezone.utc)),
    ("2019-02", datetime(2019, 2, 1, tzinfo=timezone.utc), datetime(2019, 3, 1, tzinfo=timezone.utc)),
    ("2019-03", datetime(2019, 3, 1, tzinfo=timezone.utc), datetime(2019, 4, 1, tzinfo=timezone.utc)),
    ("2019-04", datetime(2019, 4, 1, tzinfo=timezone.utc), datetime(2019, 5, 1, tzinfo=timezone.utc)),
    ("2019-05", datetime(2019, 5, 1, tzinfo=timezone.utc), datetime(2019, 6, 1, tzinfo=timezone.utc)),
    ("2019-06", datetime(2019, 6, 1, tzinfo=timezone.utc), datetime(2019, 7, 1, tzinfo=timezone.utc)),
    ("2019-07", datetime(2019, 7, 1, tzinfo=timezone.utc), datetime(2019, 8, 1, tzinfo=timezone.utc)),
    ("2019-08", datetime(2019, 8, 1, tzinfo=timezone.utc), datetime(2019, 9, 1, tzinfo=timezone.utc)),
    ("2019-09", datetime(2019, 9, 1, tzinfo=timezone.utc), datetime(2019, 10, 1, tzinfo=timezone.utc)),
    ("2019-10", datetime(2019, 10, 1, tzinfo=timezone.utc), datetime(2019, 11, 1, tzinfo=timezone.utc)),
    ("2019-11", datetime(2019, 11, 1, tzinfo=timezone.utc), datetime(2019, 12, 1, tzinfo=timezone.utc)),
    ("2019-12", datetime(2019, 12, 1, tzinfo=timezone.utc), datetime(2020, 1, 1, tzinfo=timezone.utc)),
]

async def run():
    conn = await asyncpg.connect(**DB_CONFIG)
    print("Connected to PostgreSQL.\n")

    # 1. Geographic centroid & bounds per month table-wide
    print(f"{'Month':<10} | {'Lat Range':<20} | {'Lon Range':<22} | {'Avg Lat':<8} | {'Avg Lon':<8}")
    print("-" * 75)

    for label, start_dt, end_dt in MONTHS_2019:
        row = await conn.fetchrow("""
            SELECT 
                ROUND(MIN(latitude)::numeric, 2) AS min_lat,
                ROUND(MAX(latitude)::numeric, 2) AS max_lat,
                ROUND(MIN(longitude)::numeric, 2) AS min_lon,
                ROUND(MAX(longitude)::numeric, 2) AS max_lon,
                ROUND(AVG(latitude)::numeric, 2) AS avg_lat,
                ROUND(AVG(longitude)::numeric, 2) AS avg_lon
            FROM ais_positions
            WHERE timestamp >= $1 AND timestamp < $2;
        """, start_dt, end_dt)
        lat_rng = f"{row['min_lat']} to {row['max_lat']}"
        lon_rng = f"{row['min_lon']} to {row['max_lon']}"
        print(f"{label:<10} | {lat_rng:<20} | {lon_rng:<22} | {row['avg_lat']:<8} | {row['avg_lon']:<8}")

    # 2. Inspect October 2019: AIS date coverage vs Spill dates
    print("\n=== OCTOBER 2019 AIS vs SPILL TIMESTAMPS ===")
    oct_ais = await conn.fetchrow("""
        SELECT 
            MIN(timestamp) AS min_time,
            MAX(timestamp) AS max_time,
            COUNT(*) AS pings,
            COUNT(DISTINCT vessel_id) AS vessels
        FROM ais_positions
        WHERE latitude BETWEEN 34.5 AND 35.5
          AND longitude BETWEEN 23.5 AND 24.5
          AND timestamp >= '2019-10-01'::timestamptz 
          AND timestamp < '2019-11-01'::timestamptz;
    """)
    print(f"October AIS pings in Crete corridor: {oct_ais['pings']:,} across {oct_ais['vessels']} vessels")
    print(f"Active AIS window in October:        {oct_ais['min_time']} to {oct_ais['max_time']}")

    # 3. Inspect July 2019: AIS date coverage vs Spill dates
    jul_ais = await conn.fetchrow("""
        SELECT 
            MIN(timestamp) AS min_time,
            MAX(timestamp) AS max_time,
            COUNT(*) AS pings,
            COUNT(DISTINCT vessel_id) AS vessels
        FROM ais_positions
        WHERE latitude BETWEEN 34.5 AND 35.5
          AND longitude BETWEEN 23.5 AND 24.5
          AND timestamp >= '2019-07-01'::timestamptz 
          AND timestamp < '2019-08-01'::timestamptz;
    """)
    print(f"\nJuly AIS pings in Crete corridor:    {jul_ais['pings']:,} across {jul_ais['vessels']} vessels")
    print(f"Active AIS window in July:           {jul_ais['min_time']} to {jul_ais['max_time']}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())