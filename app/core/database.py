# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# Create the async engine
# D4: pool_pre_ping validates connections; pool_recycle prevents stale connections.
# pool_size and max_overflow are configurable via Settings.
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
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