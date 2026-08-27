from datetime import datetime, timezone
from typing import List, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Centroid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)


class SpillIngestSchema(BaseModel):
    """Schema for validating incoming ML oil-spill detection data."""

    model_config = ConfigDict(extra="forbid")

    spill_id: str = Field(..., min_length=1)
    detected_at: datetime
    centroid: Centroid

    polygon: List[Tuple[float, float]] = Field(
        ...,
        min_length=4,
        description="Closed list of [longitude, latitude] coordinate pairs",
    )

    area_km2: float = Field(..., gt=0)
    estimated_age_hours: float = Field(..., ge=0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    @field_validator("detected_at")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "detected_at must include timezone information and be in UTC."
            )

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_polygon(self) -> "SpillIngestSchema":
        first_point = self.polygon[0]
        last_point = self.polygon[-1]

        if first_point != last_point:
            raise ValueError(
                "Polygon must be closed: first coordinate must equal last coordinate."
            )

        return self