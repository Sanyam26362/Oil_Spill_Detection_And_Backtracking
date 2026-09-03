from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SpillVisualization(BaseModel):
    spill_id: str

    latitude: float
    longitude: float

    detected_at: datetime


class SourceEstimateVisualization(BaseModel):
    latitude: float
    longitude: float
    radius_km: float


class WindVisualization(BaseModel):
    u: float = Field(description="East-west wind component in m/s")
    v: float = Field(description="North-south wind component in m/s")
    speed: float = Field(description="Wind speed in m/s")
    direction: float = Field(
        description="Meteorological direction the wind is coming from, degrees"
    )
    unit: str = "m/s"


class CurrentVisualization(BaseModel):
    u: float = Field(description="East-west ocean current component in m/s")
    v: float = Field(description="North-south ocean current component in m/s")
    speed: float = Field(description="Ocean current speed in m/s")
    direction: float = Field(
        description="Direction the current is moving toward, degrees"
    )
    unit: str = "m/s"


class EnvironmentVisualization(BaseModel):
    wind: WindVisualization
    current: CurrentVisualization


class TrajectoryPoint(BaseModel):
    timestamp: datetime

    latitude: float
    longitude: float


class VisualizationResponse(BaseModel):
    spill: SpillVisualization

    source_estimate: SourceEstimateVisualization

    environment: EnvironmentVisualization

    trajectory: list[TrajectoryPoint]