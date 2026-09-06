#!/usr/bin/env python3
import asyncio
import os
import sys
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


async def check():
    conn = await asyncpg.connect(**DB_CONFIG)
    print(f"Connected to '{DB_CONFIG['database']}'.\n")

    # 1. Introspect columns of ais_positions
    columns = await conn.fetch("""
        SELECT column_name, data_type, udt_name 
        FROM information_schema.columns 
        WHERE table_name = 'ais_positions' 
        ORDER BY ordinal_position;
    """)

    print("--- AIS_POSITIONS TABLE SCHEMA ---")
    col_dict = {}
    for col in columns:
        col_name = col["column_name"]
        udt = col["udt_name"]
        col_dict[col_name] = udt
        print(f"  {col_name:<20} {col['data_type']:<25} ({udt})")

    # Detect geometry / geography / coordinate columns
    geom_col = None
    lat_col = None
    lon_col = None
    time_col = None

    for name, udt in col_dict.items():
        if udt in ("geometry", "geography"):
            geom_col = name
        elif name.lower() in ("geom", "geog", "location", "point", "pos", "position") and geom_col is None:
            geom_col = name
        elif name.lower() in ("lat", "latitude"):
            lat_col = name
        elif name.lower() in ("lon", "lng", "longitude"):
            lon_col = name
        elif name.lower() in ("timestamp", "time", "ts", "datetime", "recorded_at"):
            time_col = name

    print(f"\nDetected spatial field : {geom_col or f'lat={lat_col}, lon={lon_col}'}")
    print(f"Detected timestamp field: {time_col}")

    # Build SQL spatial expression
    if geom_col:
        geom_expr = f"{geom_col}::geometry"
        geog_expr = f"{geom_col}::geography"
    elif lat_col and lon_col:
        geom_expr = f"ST_SetSRID(ST_Point({lon_col}, {lat_col}), 4326)"
        geog_expr = f"ST_SetSRID(ST_Point({lon_col}, {lat_col}), 4326)::geography"
    else:
        print("\nCould not automatically detect spatial columns. Please inspect column list above.")
        await conn.close()
        return

    time_clause = f"MIN({time_col}) AS min_time, MAX({time_col}) AS max_time," if time_col else ""

    # 2. Query spatial & temporal extents
    extent_query = f"""
        SELECT 
            {time_clause}
            ST_YMin(ST_Extent({geom_expr})) AS min_lat,
            ST_YMax(ST_Extent({geom_expr})) AS max_lat,
            ST_XMin(ST_Extent({geom_expr})) AS min_lon,
            ST_XMax(ST_Extent({geom_expr})) AS max_lon,
            COUNT(*) AS total_rows
        FROM ais_positions;
    """
    extent = await conn.fetchrow(extent_query)

    print("\n--- AIS DATABASE EXTENT ---")
    print(f"Total Rows:       {extent['total_rows']:,}")
    if time_col:
        print(f"Timestamp Range:  {extent['min_time']} to {extent['max_time']}")
    print(f"Latitude Extent:  {extent['min_lat']:.4f}° to {extent['max_lat']:.4f}°")
    print(f"Longitude Extent: {extent['min_lon']:.4f}° to {extent['max_lon']:.4f}°")

    # 3. Density check in Crete corridor (35.05°N, 24.05°E)
    vessel_id_col = "vessel_id" if "vessel_id" in col_dict else ("mmsi" if "mmsi" in col_dict else "*")
    for radius_km in [15, 30, 60]:
        density_query = f"""
            SELECT 
                COUNT(*) AS pings,
                COUNT(DISTINCT {vessel_id_col}) AS vessels
            FROM ais_positions
            WHERE ST_DWithin(
                {geog_expr}, 
                ST_SetSRID(ST_Point(24.05, 35.05), 4326)::geography, 
                $1
            );
        """
        res = await conn.fetchrow(density_query, float(radius_km * 1000))
        print(f"\nWithin {radius_km} km of spill center (35.05°N, 24.05°E):")
        print(f"  Pings:          {res['pings']:,}")
        print(f"  Unique Vessels: {res['vessels']:,}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(check())