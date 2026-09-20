from contextlib import asynccontextmanager
import logging
from pathlib import Path

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
from app.services.weather_service import WeatherService
# These imports register ORM models with Base.metadata before create_all.
from app.models.ais import AISPosition, Vessel  # noqa: F401
from app.models.spill import OilSpillDetection  # noqa: F401

__all__ = ["AISPosition", "Vessel", "OilSpillDetection"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables when the application starts
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # E7: Verify required runtime data paths exist before serving traffic.
    # Log clear logger.error (do not raise) naming path and purpose.
    required_paths = [
        (
            PROJECT_ROOT / "json_output",
            "required by SpillCatalogService for loading demo spills, detection metadata, and polygons",
        ),
        (
            PROJECT_ROOT / "data" / "weather" / "raw",
            "required by WeatherService for ERA5 10m atmospheric wind NetCDF datasets",
        ),
        (
            PROJECT_ROOT / "data" / "ocean" / "raw",
            "required by WeatherService for CMEMS hydrodynamic ocean current NetCDF datasets",
        ),
    ]
    for req_path, purpose in required_paths:
        if not req_path.exists():
            logger.error(
                "Runtime data path missing: %s (%s). Please verify volumes or populate data.",
                req_path,
                purpose,
            )

    # Initialize the in-memory catalog for the demo
    SpillCatalogService.initialize()

    # D2: Create a single shared WeatherService for the application lifetime.
    # All routers (drift, attribution, visualization) retrieve it from app.state.
    app.state.weather_service = WeatherService(
        weather_yearly_dir=(
            PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
        ),
        ocean_yearly_dir=(
            PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"
        ),
    )

    yield

    # Close database connection pool
    await engine.dispose()

    # Close the shared WeatherService (datasets + file handles).
    app.state.weather_service.close()

    # visualization.shutdown_weather_service() is now a no-op stub (D2).
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