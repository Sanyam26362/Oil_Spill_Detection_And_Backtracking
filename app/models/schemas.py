from pydantic import BaseModel,Field
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


# ============================================================
# DEMO API SCHEMAS
# ============================================================

class DemoSpillListItem(BaseModel):
    spill_id: str
    detected_at: datetime
    centroid: CentroidSchema
    area_km2: float
    confidence_score: float
    candidate_count: int
    image_url: Optional[str]


class DemoPaginationResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[DemoSpillListItem]


class DemoSpillDetail(BaseModel):
    spill_id: str
    source_type: str
    source_file: str
    detected_at: datetime
    estimated_age_hours: float
    estimated_release_time: datetime
    observation_latitude: float
    observation_longitude: float
    centroid: CentroidSchema
    polygon: List[List[float]]
    area_km2: float
    confidence_score: float
    image_url: Optional[str]
    estimated_source_latitude: Optional[float]
    estimated_source_longitude: Optional[float]
    estimated_source_radius_km: Optional[float]
    candidate_count: int
    ranked_top_vessel: Optional[str]
    ranked_top_score: Optional[float]
    runtime_seconds: Optional[float]


class DemoSpillVessel(BaseModel):
    vessel_id: str
    is_mock: bool
    is_mock_comparison: Optional[bool] = False
    rank: Optional[int] = None
    score: Optional[float] = None
    vessel_name: Optional[str] = None
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    country: Optional[str] = None
    shiptype: Optional[int] = None
    shiptype_name: Optional[str] = None
    vessel_type: Optional[str] = None
    speed: Optional[float] = None
    course: Optional[float] = None
    heading: Optional[float] = None
    distance_to_origin_km: Optional[float] = None
    time_difference_hours: Optional[float] = None
    trajectory_correlation: Optional[float] = None


class DemoSpillVesselResponse(BaseModel):
    spill_id: str
    vessels: List[DemoSpillVessel]


class DemoBacktrackResponse(BaseModel):
    spill_id: str
    backtrack: dict
    attribution: dict

class DemoVesselEvidencePoint(BaseModel):
    timestamp: datetime
    latitude: float
    longitude: float
    speed: Optional[float] = None
    course: Optional[float] = None
    heading: Optional[float] = None


class DemoVesselEvidence(BaseModel):
    vessel_id: str
    is_mock: bool
    is_mock_comparison: Optional[bool] = False
    rank: Optional[int] = None
    score: Optional[float] = None

    vessel_name: Optional[str] = None
    mmsi: Optional[str] = None
    imo: Optional[str] = None

    country: Optional[str] = None
    vessel_type: Optional[str] = None

    culprit_location: Optional[
        DemoVesselEvidencePoint
    ] = None

    distance_from_backtrack_origin_km: Optional[
        float
    ] = None
    distance_to_origin_km: Optional[float] = None

    full_trajectory_point_count: Optional[int] = 0
    trajectory_correlation: Optional[float] = None
    speed: Optional[float] = None
    course: Optional[float] = None
    heading: Optional[float] = None
    time_difference_hours: Optional[float] = None

    trajectory: List[
        DemoVesselEvidencePoint
    ] = Field(default_factory=list)


class DemoAttributionTrajectoryResponse(BaseModel):
    spill_id: str

    backtrack_origin: dict

    verification: dict

    attribution: dict

    vessels: List[
        DemoVesselEvidence
    ]