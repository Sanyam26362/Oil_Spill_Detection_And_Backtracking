# app/database.py
import socket
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# Handle IPv4 forcing and local DNS resolution for Neon cloud endpoints
_orig_getaddrinfo = socket.getaddrinfo
def _neon_dns_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    # Force IPv4 (AF_INET) for neon.tech to prevent IPv6 [Errno 111] Connection Refused
    # on IPv4-only cloud container runtimes (such as Render, Fly, or Docker)
    if "neon.tech" in str(host):
        family = socket.AF_INET
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if "neon.tech" in str(host):
            return _orig_getaddrinfo("3.147.219.177", port, socket.AF_INET, type, proto, flags)
        raise

socket.getaddrinfo = _neon_dns_getaddrinfo

# Create the async engine
# D4: pool_pre_ping validates connections; pool_recycle prevents stale connections.
# pool_size and max_overflow are configurable via Settings.
connect_args = {}
if settings.NEON_URL or "neon.tech" in settings.async_database_url:
    connect_args["ssl"] = "require"

engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=connect_args,
)

# Create a configured "AsyncSession" class
AsyncSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Create a Base class for declarative models
Base = declarative_base()

# Dependency to yield the database session to FastAPI routes
async def get_db():
    """
    Yields an async database session for dependency injection in FastAPI.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()