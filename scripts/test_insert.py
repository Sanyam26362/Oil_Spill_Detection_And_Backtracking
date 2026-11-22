import os
import asyncio
import socket
from dotenv import load_dotenv
import asyncpg

orig_getaddrinfo = socket.getaddrinfo
def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if 'neon.tech' in host:
        return orig_getaddrinfo('3.147.219.177', port, family, type, proto, flags)
    return orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = custom_getaddrinfo

async def test():
    load_dotenv('d:/projects/oil-spill-backend/.env')
    conn = await asyncpg.connect(os.getenv('NEON_URL'))
    await conn.execute("INSERT INTO vessels (vessel_id, country, shiptype, shiptype_name) VALUES ('TEST-001', 'GR', 70, 'Cargo') ON CONFLICT DO NOTHING;")
    await conn.execute("""
        INSERT INTO ais_positions (vessel_id, timestamp, longitude, latitude, speed, course, heading, geometry, is_synthetic, scenario_id)
        VALUES ('TEST-001', NOW(), 24.0, 35.0, 10.0, 180.0, 180.0, ST_SetSRID(ST_MakePoint(24.0, 35.0), 4326), true, 'test')
    """)
    cnt = await conn.fetchval("SELECT count(*) FROM ais_positions WHERE vessel_id = 'TEST-001';")
    print("AIS insert success, count:", cnt)
    await conn.execute("DELETE FROM vessels WHERE vessel_id = 'TEST-001';")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(test())
