from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.core.database import Base, engine
from app.routers import spills
from app.models.ais import AISPosition, Vessel
from app.models.spill import OilSpill

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables when the application starts
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Close the
    #  database connection pool when the application shuts down
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)


# Register spill-related API routes
app.include_router(
    spills.router,
    prefix=f"{settings.API_V1_STR}/spills",
    tags=["ML Pipeline Ingestion"],
)


@app.get("/health", tags=["System"])
async def health_check():
    """Check whether the API is running."""
    return {
        "status": "operational",
        "service": settings.PROJECT_NAME,
    }