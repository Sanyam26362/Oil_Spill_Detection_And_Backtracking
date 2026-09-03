from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine, AsyncSessionLocal
from app.routers import (
    spills,
    drift,
    attribution,
    demo_spills,
    visualization,
)
from app.services.spill_catalog_service import SpillCatalogService
from app.models.ais import AISPosition, Vessel
from app.models.spill import OilSpillDetection


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables when the application starts
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize the in-memory catalog for the demo
    SpillCatalogService.initialize()

    yield

    # Close database connection pool
    await engine.dispose()

    # Close visualization weather service
    visualization.shutdown_weather_service()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)


# Setup CORS

origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Existing APIs
# ---------------------------------------------------------

app.include_router(
    spills.router,
    prefix=f"{settings.API_V1_STR}/spills",
    tags=["ML Pipeline Ingestion"],
)

app.include_router(
    drift.router,
    prefix=f"{settings.API_V1_STR}/drift",
    tags=["Drift Modeling"],
)

app.include_router(
    attribution.router,
    prefix=f"{settings.API_V1_STR}/attribution",
    tags=["Attribution"],
)

app.include_router(
    demo_spills.router,
    prefix=f"{settings.API_V1_STR}/demo/spills",
    tags=["Demo API"],
)


# ---------------------------------------------------------
# NEW Visualization API
# ---------------------------------------------------------

app.include_router(
    visualization.router,
    prefix=f"{settings.API_V1_STR}/visualization",
    tags=["Visualization"],
)


# ---------------------------------------------------------
# Health checks
# ---------------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check():
    """Check whether the API is running."""

    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
    }


@app.get("/health/ready", tags=["System"])
async def health_ready():
    """Check if the database and essential services are ready."""

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))

        return {
            "status": "ready"
        }

    except Exception as e:
        return {
            "status": "unready",
            "detail": str(e),
        }