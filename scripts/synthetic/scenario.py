from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SyntheticScenarioConfig:
    """
    Configuration for one synthetic oil-spill attribution experiment.

    The configuration contains both:
    - the physical oil-release event
    - the AIS traffic-generation parameters

    Ground truth is used only by the evaluation layer.
    """

    scenario_id: str

    # ==============================================================
    # TRUE OIL RELEASE
    # ==============================================================

    release_lat: float
    release_lon: float
    release_time: datetime

    # ==============================================================
    # SYNTHETIC SAR OBSERVATION
    # ==============================================================

    observation_lat: float
    observation_lon: float
    observation_time: datetime

    drift_duration_hours: float

    # ==============================================================
    # AIS GENERATION REGION
    # ==============================================================

    bounds_lat_min: float
    bounds_lat_max: float

    bounds_lon_min: float
    bounds_lon_max: float

    # ==============================================================
    # FLEET
    # ==============================================================

    num_background_vessels: int = 150

    num_decoy_vessels: int = 8

    # Globally unique vessel ID prefix per scenario.
    # Example: "SYNTH-S001-" produces "SYNTH-S001-SRC", "SYNTH-S001-BKG0001"
    vessel_id_prefix: str = "SYNTH-"

    source_vessel_id: str = "SYNTH-000011"

    decoy_start_id: int = 12

    # Explicit decoy behaviors to inject specific challenges.
    # If empty, fallback to default decoy generator logic.
    decoy_behaviors: list[str] = field(default_factory=list)

    # ==============================================================
    # SOURCE-VESSEL BEHAVIOR
    # ==============================================================

    approach_start_distance_km: float = 30.0

    approach_duration_hours: float = 2.0

    slowdown_duration_minutes: int = 40

    loiter_duration_minutes: int = 30

    departure_duration_hours: float = 3.0

    approach_speed_knots: float = 10.0

    slowdown_speed_knots: float = 2.5

    release_speed_knots: float = 0.8

    departure_speed_knots: float = 11.0

    # ==============================================================
    # OIL MODEL
    # ==============================================================

    windage: float = 0.03

    # ==============================================================
    # RANDOMNESS
    # ==============================================================

    seed: int = 42