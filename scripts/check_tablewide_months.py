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
    print("Connected to PostgreSQL. Checking all 92M rows month-by-month table-wide...\n")
    print(f"{'Month':<10} | {'Total Pings Table-Wide':<25} | {'Vessels Table-Wide':<20}")
    print("-" * 60)

    for label, start_dt, end_dt in MONTHS_2019:
        row = await conn.fetchrow("""
            SELECT 
                COUNT(*) AS pings,
                COUNT(DISTINCT vessel_id) AS vessels
            FROM ais_positions
            WHERE timestamp >= $1 
              AND timestamp < $2;
        """, start_dt, end_dt)
        print(f"{label:<10} | {row['pings']:<25,} | {row['vessels']:<20,}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())