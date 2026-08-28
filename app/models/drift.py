from dataclasses import dataclass
from datetime import datetime


@dataclass
class EnvironmentalVelocity:
    """
    Environmental velocity at a specific location and time.

    Wind:
        wind_u -> east-west component (m/s)
        wind_v -> north-south component (m/s)

    Ocean current:
        current_u -> east-west component (m/s)
        current_v -> north-south component (m/s)
    """

    wind_u: float
    wind_v: float

    current_u: float
    current_v: float


@dataclass
class DriftVelocity:
    """
    Resulting surface drift velocity.

    u -> east-west component (m/s)
    v -> north-south component (m/s)
    """

    u: float
    v: float


@dataclass
class ParticleState:
    """
    State of an oil particle at a specific timestamp.

    This represents the particle position at exactly
    `timestamp`.
    """

    timestamp: datetime

    latitude: float
    longitude: float

    wind_u: float
    wind_v: float

    current_u: float
    current_v: float

    drift_u: float
    drift_v: float


@dataclass
class DriftTrajectory:
    """
    Ordered particle trajectory.

    First state = initial position.
    Every subsequent state = position after one timestep.
    """

    states: list[ParticleState]

    @property
    def start(self) -> ParticleState:
        if not self.states:
            raise ValueError("Trajectory contains no states.")

        return self.states[0]

    @property
    def end(self) -> ParticleState:
        if not self.states:
            raise ValueError("Trajectory contains no states.")

        return self.states[-1]


@dataclass
class ParticleSource:
    """
    Estimated origin of one backward-tracked particle.
    """

    latitude: float
    longitude: float
    timestamp: datetime


@dataclass
class SourceEstimate:
    """
    Aggregate result from a backward particle ensemble.
    """

    particles: list[ParticleSource]

    centroid_latitude: float
    centroid_longitude: float

    radius_km: float