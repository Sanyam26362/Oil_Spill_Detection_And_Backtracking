from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class VesselLocationResponse(BaseModel):
    vessel_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed: Optional[float] = None
    course: Optional[float] = None
    heading: Optional[float] = None
    vessel_type: Optional[str] = None
    country: Optional[str] = None
    is_synthetic: bool
    scenario_id: Optional[str] = None