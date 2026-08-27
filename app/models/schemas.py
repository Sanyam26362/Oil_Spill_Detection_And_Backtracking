# app/models/schemas.py
from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import List, Tuple

class Centroid(BaseModel):
    lon: float
    lat: float

class SpillIngestSchema(BaseModel):
    """Schema for validating the incoming ML payload"""
    spill_id: str
    detected_at: datetime
    centroid: Centroid
    polygon: List[Tuple[float, float]] = Field(..., description="List of [lon, lat] coordinates")
    area_km2: float
    estimated_age_hours: float
    confidence_score: float

    @model_validator(mode='after')
    def check_closed_ring(self) -> 'SpillIngestSchema':
        # Strict Rule: Polygon must be a closed ring (first coordinate == last coordinate)
        if len(self.polygon) < 4:
            raise ValueError("Polygon must have at least 4 points to form a closed ring.")
        
        first_point = self.polygon[0]
        last_point = self.polygon[-1]
        
        if first_point != last_point:
            raise ValueError(f"Polygon is not closed. First point {first_point} != Last point {last_point}")
        return self