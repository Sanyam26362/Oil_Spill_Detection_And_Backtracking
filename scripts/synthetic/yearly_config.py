from dataclasses import dataclass


@dataclass(frozen=True)
class YearlyAISConfig:
    """Configuration for persistent synthetic AIS background traffic."""

    year: int = 2019

    # Start small for the prototype.
    num_vessels: int = 200

    # Conservative interior of the intended Eastern Mediterranean
    # environmental domain.
    region_min_lat: float = 30.5
    region_max_lat: float = 36.5

    region_min_lon: float = 23.0
    region_max_lon: float = 35.75

    # Reproducible generation.
    seed: int = 2026

    # Calibration defaults derived from the inspected Piraeus AIS reference.
    # These are configurable assumptions, not universal AIS statistics.
    missing_heading_rate: float = 0.3819
    missing_course_rate: float = 0.1223
    missing_speed_rate: float = 0.0027