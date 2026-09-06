#!/usr/bin/env python3
import asyncio
import asyncpg

DB_CONFIG = {
    "user": "sih_admin",
    "password": "sih_secure_password_2026",
    "database": "oil_spill_db",
    "host": "localhost",
    "port": 5432,
}

async def run():
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT 
            to_char(timestamp, 'YYYY-MM') AS month,
            scenario_id,
            COUNT(DISTINCT vessel_id) AS vessels,
            COUNT(*) AS pings
        FROM ais_positions
        WHERE latitude BETWEEN 34.5 AND 35.5
          AND longitude BETWEEN 23.5 AND 24.5
        GROUP BY 1, 2
        ORDER BY 1, 2;
    """)
    print(f"{'Month':<10} | {'Scenario':<18} | {'Vessels':<10} | {'Pings':<10}")
    print("-" * 55)
    for r in rows:
        print(f"{r['month']:<10} | {str(r['scenario_id']):<18} | {r['vessels']:<10} | {r['pings']:,}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())