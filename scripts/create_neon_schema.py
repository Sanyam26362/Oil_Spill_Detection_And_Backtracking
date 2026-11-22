import os
import asyncio
import socket
from dotenv import load_dotenv
import asyncpg

# Custom DNS resolver for Neon on local network if router fails
orig_getaddrinfo = socket.getaddrinfo
def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if 'neon.tech' in host:
        return orig_getaddrinfo('3.147.219.177', port, family, type, proto, flags)
    return orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = custom_getaddrinfo

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS spills_catalog (
    spill_id VARCHAR(64) PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL,
    centroid_lat DOUBLE PRECISION NOT NULL,
    centroid_lon DOUBLE PRECISION NOT NULL,
    area_km2 DOUBLE PRECISION NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    ranked_top_vessel VARCHAR(64),
    ranked_top_score DOUBLE PRECISION,
    image_url TEXT,
    polygon JSONB,
    detail_payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS spill_visualizations (
    spill_id VARCHAR(64) PRIMARY KEY REFERENCES spills_catalog(spill_id) ON DELETE CASCADE,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS spill_vessels (
    spill_id VARCHAR(64) PRIMARY KEY REFERENCES spills_catalog(spill_id) ON DELETE CASCADE,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS spill_attributions (
    spill_id VARCHAR(64) PRIMARY KEY REFERENCES spills_catalog(spill_id) ON DELETE CASCADE,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS spill_forecasts (
    spill_id VARCHAR(64) PRIMARY KEY REFERENCES spills_catalog(spill_id) ON DELETE CASCADE,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS spill_backtracks (
    spill_id VARCHAR(64) PRIMARY KEY REFERENCES spills_catalog(spill_id) ON DELETE CASCADE,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS diagnostic_plots (
    spill_id VARCHAR(64) PRIMARY KEY,
    plot_url TEXT
);

CREATE TABLE IF NOT EXISTS vessels (
    vessel_id VARCHAR(64) PRIMARY KEY,
    country VARCHAR(100),
    shiptype INTEGER,
    shiptype_name VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS ais_positions (
    id SERIAL PRIMARY KEY,
    vessel_id VARCHAR(64) NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    speed DOUBLE PRECISION,
    course DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    geometry geometry(Point, 4326),
    is_synthetic BOOLEAN DEFAULT TRUE,
    scenario_id VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_ais_positions_vessel_timestamp ON ais_positions(vessel_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ais_positions_geom ON ais_positions USING gist(geometry);
CREATE INDEX IF NOT EXISTS idx_spills_catalog_detected_at ON spills_catalog(detected_at);
"""

async def main():
    load_dotenv('d:/projects/oil-spill-backend/.env')
    u = os.getenv('NEON_URL')
    if not u:
        raise ValueError("NEON_URL not found in .env")
    
    print("Connecting to Neon...")
    conn = await asyncpg.connect(u)
    print("Executing schema creation...")
    await conn.execute(SCHEMA_SQL)
    print("Schema created successfully!")

    tables = await conn.fetch("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' ORDER BY table_name;
    """)
    print("Current tables in Neon:", [r['table_name'] for r in tables])
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
