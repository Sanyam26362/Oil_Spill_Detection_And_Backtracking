from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# ============================================================
# ML INGESTION SCHEMAS
# ============================================================

class CentroidSchema(BaseModel):
    lon: float
    lat: float


class SpillDetectionItem(BaseModel):
    spill_id: str
    detected_at: datetime
    centroid: CentroidSchema
    polygon: List[List[float]]
    area_km2: float
    estimated_age_hours: float
    confidence_score: float
    image_reference: str


class MLPredictionPayload(BaseModel):
    detections: List[SpillDetectionItem]


# ============================================================
# FRONTEND RESPONSE SCHEMAS
# ============================================================

class TrajectoryPoint(BaseModel):
    lat: float
    lon: float
    timestamp: datetime


class CandidateVessel(BaseModel):
    vessel_id: str
    vessel_name: Optional[str] = None
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    attribution_score: float
    distance_to_origin_km: float
    time_difference_hours: float
    trajectory_correlation: float


class SpillOrigin(BaseModel):
    lat: float
    lon: float
    timestamp: datetime
    confidence: float


class BacktrackResponse(BaseModel):
    spill: SpillDetectionItem
    origin: SpillOrigin
    backward_trajectory: List[TrajectoryPoint]
    forward_trajectory: List[TrajectoryPoint]
    candidate_vessels: List[CandidateVessel]