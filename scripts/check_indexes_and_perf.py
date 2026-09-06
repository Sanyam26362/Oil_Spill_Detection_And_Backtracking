#!/usr/bin/env python3
import asyncio
import os
import sys
import time
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

async def inspect():
    conn = await asyncpg.connect(**DB_CONFIG)
    print("Connected to PostgreSQL.\n")

    # 1. Inspect existing indexes on ais_positions
    indexes = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'ais_positions';
    """)
    print("=== INDEXES ON ais_positions ===")
    for idx in indexes:
        print(f"• {idx['indexname']}: {idx['indexdef']}")

    # 2. Inspect scenario_id & is_synthetic distribution within 30 km of spill cluster
    print("\n=== SCENARIOS PRESENT IN THE 30 KM SPILL CORRIDOR ===")
    scenarios = await conn.fetch("""
        SELECT 
            COALESCE(scenario_id, 'NULL') AS scenario_id,
            is_synthetic,
            COUNT(DISTINCT vessel_id) AS vessels,
            COUNT(*) AS pings
        FROM ais_positions
        WHERE latitude BETWEEN 34.75 AND 35.35
          AND longitude BETWEEN 23.70 AND 24.40
        GROUP BY scenario_id, is_synthetic;
    """)
    for row in scenarios:
        print(f"• scenario_id: {row['scenario_id']:<18} | is_synthetic: {str(row['is_synthetic']):<5} | vessels: {row['vessels']:<4} | pings: {row['pings']:,}")

    # 3. Benchmark a sample query using bounding box + distance
    print("\n=== QUERY PERFORMANCE BENCHMARK (Testing 1 Detection Window) ===")
    t0 = time.perf_counter()
    sample = await conn.fetchrow("""
        EXPLAIN ANALYZE
        SELECT COUNT(DISTINCT vessel_id)
        FROM ais_positions
        WHERE timestamp BETWEEN '2019-01-21 05:44:10+00' AND '2019-01-21 09:44:10+00'
          AND latitude BETWEEN 34.70 AND 35.00
          AND longitude BETWEEN 24.05 AND 24.40
          AND ST_DWithin(
                geometry,
                ST_SetSRID(ST_Point(24.2276, 34.8551), 4326),
                0.09  -- approx 10 km in degrees
          );
    """)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"Sample spatial+temporal query took: {elapsed:.2f} ms")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect())