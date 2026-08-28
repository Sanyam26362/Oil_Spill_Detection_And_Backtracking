from dataclasses import dataclass
from datetime import datetime


@dataclass
class SpillScenario:
    scenario_id: str

    origin_lat: float
    origin_lon: float

    origin_time: datetime

    region_min_lat: float
    region_max_lat: float
    region_min_lon: float
    region_max_lon: float

    duration_hours: int = 24

    background_vessels: int = 150
    candidate_vessels: int = 5

    suspicious_vessel_index: int = 0