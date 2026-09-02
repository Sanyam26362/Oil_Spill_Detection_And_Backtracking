from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .scenario import SyntheticScenarioConfig


KNOTS_TO_MS = 0.514444444
EARTH_RADIUS_M = 6_371_000.0


# -------------------------------------------------------------------
# TIME
# -------------------------------------------------------------------

def utc_timestamp(value: datetime | pd.Timestamp) -> pd.Timestamp:
    """
    Convert a datetime into UTC-aware pandas Timestamp.
    """

    ts = pd.Timestamp(value)

    if ts.tzinfo is None:
        return ts.tz_localize("UTC")

    return ts.tz_convert("UTC")


def iso_utc(value: datetime | pd.Timestamp) -> str:
    """
    Always emit clean UTC timestamps:

        2019-07-15T12:00:00Z
    """

    ts = utc_timestamp(value)

    return (
        ts.isoformat()
        .replace("+00:00", "Z")
    )


# -------------------------------------------------------------------
# GEOGRAPHY
# -------------------------------------------------------------------

def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:

    radius_km = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2.0) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dlon / 2.0) ** 2
    )

    return (
        2.0
        * radius_km
        * math.asin(math.sqrt(a))
    )


def bearing_between(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    dlon = math.radians(lon2 - lon1)

    x = (
        math.sin(dlon)
        * math.cos(lat2_rad)
    )

    y = (
        math.cos(lat1_rad)
        * math.sin(lat2_rad)
        -
        math.sin(lat1_rad)
        * math.cos(lat2_rad)
        * math.cos(dlon)
    )

    return (
        math.degrees(
            math.atan2(x, y)
        )
        + 360.0
    ) % 360.0


def move_vessel(
    latitude: float,
    longitude: float,
    course_deg: float,
    speed_knots: float,
    seconds: float,
) -> tuple[float, float]:

    speed_ms = speed_knots * KNOTS_TO_MS

    course_rad = math.radians(course_deg)

    north_velocity = (
        speed_ms * math.cos(course_rad)
    )

    east_velocity = (
        speed_ms * math.sin(course_rad)
    )

    north_distance = (
        north_velocity * seconds
    )

    east_distance = (
        east_velocity * seconds
    )

    delta_lat = math.degrees(
        north_distance / EARTH_RADIUS_M
    )

    cos_lat = math.cos(
        math.radians(latitude)
    )

    if abs(cos_lat) < 1e-12:
        raise ValueError(
            "Longitude calculation unstable near poles."
        )

    delta_lon = math.degrees(
        east_distance
        / (EARTH_RADIUS_M * cos_lat)
    )

    return (
        latitude + delta_lat,
        longitude + delta_lon,
    )


# -------------------------------------------------------------------
# AIS RECORD
# -------------------------------------------------------------------

def add_record(
    records: list[dict],
    vessel_id: str,
    timestamp: pd.Timestamp,
    latitude: float,
    longitude: float,
    speed: float,
    course: float,
    heading: float,
    vessel_type: str,
    country: str,
    scenario_id: str,
) -> None:

    records.append(
        {
            "vessel_id": vessel_id,
            "timestamp": iso_utc(timestamp),
            "longitude": round(longitude, 7),
            "latitude": round(latitude, 7),
            "speed": round(
                max(0.0, speed),
                2,
            ),
            "course": round(
                course % 360.0,
                2,
            ),
            "heading": round(
                heading % 360.0,
                2,
            ),
            "vessel_type": vessel_type,
            "country": country,
            "is_synthetic": True,
            "scenario_id": scenario_id,
        }
    )


# -------------------------------------------------------------------
# REPORTING INTERVAL
# -------------------------------------------------------------------

def sample_reporting_interval(
    rng: np.random.Generator,
    moving: bool = True,
) -> int:
    """
    Approximate the observed Piraeus reporting behavior.

    These probabilities are deliberately approximate rather than
    claiming to reproduce the exact empirical distribution.
    """

    intervals = np.array(
        [11, 28, 180, 358, 1111],
        dtype=int,
    )

    if moving:
        probabilities = np.array(
            [0.48, 0.27, 0.13, 0.08, 0.04]
        )
    else:
        probabilities = np.array(
            [0.15, 0.20, 0.25, 0.25, 0.15]
        )

    return int(
        rng.choice(
            intervals,
            p=probabilities,
        )
    )


# -------------------------------------------------------------------
# VESSEL TYPE
# -------------------------------------------------------------------

def sample_vessel_type(
    rng: np.random.Generator,
) -> str:

    types = [
        "Cargo",
        "Tanker",
        "Passenger",
        "Pleasure Craft",
        "Tug",
        "Fishing",
    ]

    weights = np.array(
        [70, 80, 60, 37, 52, 30],
        dtype=float,
    )

    weights /= weights.sum()

    return str(
        rng.choice(
            types,
            p=weights,
        )
    )


# -------------------------------------------------------------------
# BACKGROUND TRACKS
# -------------------------------------------------------------------

def generate_background_vessel(
    scenario: SyntheticScenarioConfig,
    vessel_number: int,
    rng: np.random.Generator,
) -> pd.DataFrame:

    prefix = getattr(scenario, 'vessel_id_prefix', 'SYNTH-')
    if scenario.scenario_id == "scenario-003":
        vessel_id = f"{prefix}BG{vessel_number:03d}"
    else:
        vessel_id = f"{prefix}BKG{vessel_number:04d}"

    vessel_type = sample_vessel_type(rng)

    start_time = (
        utc_timestamp(scenario.release_time)
        - pd.Timedelta(hours=4)
    )

    end_time = (
        start_time
        + pd.Timedelta(
            hours=10
        )
    )

    start_lat = rng.uniform(
        scenario.bounds_lat_min,
        scenario.bounds_lat_max,
    )

    start_lon = rng.uniform(
        scenario.bounds_lon_min,
        scenario.bounds_lon_max,
    )

    end_lat = rng.uniform(
        scenario.bounds_lat_min,
        scenario.bounds_lat_max,
    )

    end_lon = rng.uniform(
        scenario.bounds_lon_min,
        scenario.bounds_lon_max,
    )

    target_speed = rng.uniform(
        5.0,
        18.0,
    )

    current_lat = start_lat
    current_lon = start_lon
    current_time = start_time

    records: list[dict] = []

    while current_time <= end_time:

        remaining_seconds = (
            end_time - current_time
        ).total_seconds()

        if remaining_seconds <= 0:
            break

        distance_remaining = haversine_km(
            current_lat,
            current_lon,
            end_lat,
            end_lon,
        )

        if distance_remaining < 0.05:
            break

        course = bearing_between(
            current_lat,
            current_lon,
            end_lat,
            end_lon,
        )

        interval = sample_reporting_interval(
            rng,
            moving=True,
        )

        interval = min(
            interval,
            int(remaining_seconds),
        )

        # Prevent overshooting the final waypoint.
        speed = max(
            0.5,
            target_speed
            + rng.normal(0.0, 0.25),
        )

        max_distance_km = (
            speed
            * 1.852
            * interval
            / 3600.0
        )

        if (
            max_distance_km
            >= distance_remaining
        ):
            interval = max(
                1,
                int(
                    distance_remaining
                    / (
                        speed
                        * 1.852
                        / 3600.0
                    )
                ),
            )

        add_record(
            records,
            vessel_id,
            current_time,
            current_lat,
            current_lon,
            speed,
            course,
            course + rng.normal(0, 2),
            vessel_type,
            "UN",
            scenario.scenario_id,
        )

        current_lat, current_lon = move_vessel(
            current_lat,
            current_lon,
            course,
            speed,
            interval,
        )

        current_time += pd.Timedelta(
            seconds=interval
        )

    # Exact endpoint prevents accumulated drift
    # from causing runaway tracks.
    add_record(
        records,
        vessel_id,
        end_time,
        end_lat,
        end_lon,
        0.0,
        0.0,
        0.0,
        vessel_type,
        "UN",
        scenario.scenario_id,
    )

    return pd.DataFrame(records)


# -------------------------------------------------------------------
# SOURCE VESSEL
# -------------------------------------------------------------------

def generate_source_vessel(
    scenario: SyntheticScenarioConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:

    release_time = utc_timestamp(
        scenario.release_time
    )

    start_time = (
        release_time
        - pd.Timedelta(
            hours=scenario.approach_duration_hours
        )
        - pd.Timedelta(minutes=40)
    )

    departure_end = (
        release_time
        + pd.Timedelta(
            hours=scenario.departure_duration_hours
        )
    )

    # Random approach direction.
    approach_bearing = float(
        rng.uniform(0, 360)
    )

    start_lat, start_lon = move_vessel(
        scenario.release_lat,
        scenario.release_lon,
        (approach_bearing + 180) % 360,
        scenario.approach_start_distance_km
        / (
            scenario.approach_speed_knots
            * 1.852
            / 3600
        ),
        1,
    )

    # The previous expression is only used to derive a directionally
    # offset point. Use a proper geographic destination below.
    angular_distance = (
        scenario.approach_start_distance_km
        / 6371.0088
    )

    lat1 = math.radians(
        scenario.release_lat
    )

    lon1 = math.radians(
        scenario.release_lon
    )

    bearing = math.radians(
        (approach_bearing + 180) % 360
    )

    lat2 = math.asin(
        math.sin(lat1)
        * math.cos(angular_distance)
        +
        math.cos(lat1)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing)
        * math.sin(angular_distance)
        * math.cos(lat1),
        math.cos(angular_distance)
        -
        math.sin(lat1)
        * math.sin(lat2),
    )

    start_lat = math.degrees(lat2)
    start_lon = math.degrees(lon2)

    records: list[dict] = []

    # ---------------------------------------------------------------
    # APPROACH
    # ---------------------------------------------------------------

    current_lat = start_lat
    current_lon = start_lon
    current_time = start_time

    approach_end = (
        release_time
        - pd.Timedelta(
            minutes=60
        )
    )

    while current_time < approach_end:

        course = bearing_between(
            current_lat,
            current_lon,
            scenario.release_lat,
            scenario.release_lon,
        )

        speed = max(
            0.1,
            scenario.approach_speed_knots
            + rng.normal(0, 0.25),
        )

        interval = 30

        add_record(
            records,
            scenario.source_vessel_id,
            current_time,
            current_lat,
            current_lon,
            speed,
            course,
            course + rng.normal(0, 1),
            "Tanker",
            "GR",
            scenario.scenario_id,
        )

        current_lat, current_lon = move_vessel(
            current_lat,
            current_lon,
            course,
            speed,
            interval,
        )

        current_time += pd.Timedelta(
            seconds=interval
        )

    # ---------------------------------------------------------------
    # SLOWDOWN
    # ---------------------------------------------------------------

    slowdown_start = (
        release_time
        - pd.Timedelta(
            minutes=scenario.slowdown_duration_minutes
        )
    )

    current_time = max(
        current_time,
        slowdown_start,
    )

    # Move toward the source but progressively slow.
    while current_time < release_time:

        course = bearing_between(
            current_lat,
            current_lon,
            scenario.release_lat,
            scenario.release_lon,
        )

        distance = haversine_km(
            current_lat,
            current_lon,
            scenario.release_lat,
            scenario.release_lon,
        )

        seconds_remaining = (release_time - current_time).total_seconds()

        interval = sample_reporting_interval(rng, moving=True)
        interval = min(interval, int(seconds_remaining))
        if interval <= 0:
            break

        speed = max(
            scenario.release_speed_knots,
            scenario.slowdown_speed_knots
            + rng.normal(0, 0.15),
        )

        max_distance_km = (
            speed * 1.852 * interval / 3600.0
        )

        if interval == int(seconds_remaining) or max_distance_km >= distance:
            interval = int(seconds_remaining)
            if interval > 0:
                speed = (distance * 3600.0) / (interval * 1.852)
            current_lat = scenario.release_lat
            current_lon = scenario.release_lon
        else:
            current_lat, current_lon = move_vessel(
                current_lat,
                current_lon,
                course,
                speed,
                interval,
            )

        add_record(
            records,
            scenario.source_vessel_id,
            current_time,
            current_lat,
            current_lon,
            speed,
            course,
            course,
            "Tanker",
            "GR",
            scenario.scenario_id,
        )

        current_time += pd.Timedelta(seconds=interval)

    # ---------------------------------------------------------------
    # EXACT RELEASE RECORD
    # ---------------------------------------------------------------

    add_record(
        records,
        scenario.source_vessel_id,
        release_time,
        scenario.release_lat,
        scenario.release_lon,
        scenario.release_speed_knots,
        approach_bearing,
        approach_bearing,
        "Tanker",
        "GR",
        scenario.scenario_id,
    )

    # ---------------------------------------------------------------
    # LOITER
    # ---------------------------------------------------------------

    loiter_end = (
        release_time
        + pd.Timedelta(
            minutes=scenario.loiter_duration_minutes
        )
    )

    current_time = (
        release_time
        + pd.Timedelta(seconds=30)
    )

    while current_time <= loiter_end:

        radius_km = rng.uniform(
            0.05,
            0.25,
        )

        angle = rng.uniform(
            0,
            360,
        )

        # Small circle around source.
        angle_rad = math.radians(angle)

        dlat = (
            radius_km
            * math.cos(angle_rad)
            / 111.32
        )

        dlon = (
            radius_km
            * math.sin(angle_rad)
            / (
                111.32
                * math.cos(
                    math.radians(
                        scenario.release_lat
                    )
                )
            )
        )

        lat = (
            scenario.release_lat
            + dlat
        )

        lon = (
            scenario.release_lon
            + dlon
        )

        add_record(
            records,
            scenario.source_vessel_id,
            current_time,
            lat,
            lon,
            max(
                0.5,
                1.2 + rng.normal(0, 0.15),
            ),
            rng.uniform(0, 360),
            rng.uniform(0, 360),
            "Tanker",
            "GR",
            scenario.scenario_id,
        )

        current_time += pd.Timedelta(
            seconds=30
        )

    # ---------------------------------------------------------------
    # DEPARTURE
    # ---------------------------------------------------------------

    departure_course = (
        approach_bearing + 180
    ) % 360

    current_lat = scenario.release_lat
    current_lon = scenario.release_lon
    current_time = loiter_end

    while current_time <= departure_end:

        minutes_after = (
            current_time
            - loiter_end
        ).total_seconds() / 60.0

        speed = min(
            scenario.departure_speed_knots,
            2.0 + minutes_after * 0.15,
        )

        speed = max(
            1.0,
            speed + rng.normal(0, 0.2),
        )

        add_record(
            records,
            scenario.source_vessel_id,
            current_time,
            current_lat,
            current_lon,
            speed,
            departure_course,
            departure_course + rng.normal(0, 1),
            "Tanker",
            "GR",
            scenario.scenario_id,
        )

        current_lat, current_lon = move_vessel(
            current_lat,
            current_lon,
            departure_course,
            speed,
            30,
        )

        current_time += pd.Timedelta(
            seconds=30
        )

    return pd.DataFrame(records)


# -------------------------------------------------------------------
# DECOYS
# -------------------------------------------------------------------

def generate_decoy_vessel(
    scenario: SyntheticScenarioConfig,
    decoy_index: int,
    rng: np.random.Generator,
) -> pd.DataFrame:

    release_time = utc_timestamp(scenario.release_time)
    start_time = release_time - pd.Timedelta(hours=4)
    end_time = release_time + pd.Timedelta(hours=6)

    prefix = getattr(scenario, 'vessel_id_prefix', 'SYNTH-')
    if scenario.scenario_id == "scenario-003":
        vessel_id = f"{prefix}DCY{scenario.decoy_start_id + decoy_index:02d}"
    else:
        vessel_id = f"{prefix}DCY{scenario.decoy_start_id + decoy_index:04d}"
    vessel_type = ["Tanker", "Cargo", "Tanker", "Passenger", "Tanker", "Fishing"][decoy_index % 6]

    if scenario.decoy_behaviors and decoy_index < len(scenario.decoy_behaviors):
        b_type = scenario.decoy_behaviors[decoy_index]
    else:
        b_type = decoy_index % 6

    target_time = release_time
    target_lat = scenario.release_lat
    target_lon = scenario.release_lon
    target_speed = 12.0
    slowdown = False
    loiter = False
    early_departure = False
    fly_through = False

    if b_type == 0:
        target_lat += rng.uniform(-0.02, 0.02)
        target_lon += rng.uniform(-0.02, 0.02)
        target_speed = rng.uniform(12.0, 16.0)
    elif b_type == 1:
        target_lat += rng.uniform(0.03, 0.06) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.03, 0.06) * rng.choice([-1, 1])
        target_speed = 4.0
        slowdown = True
    elif b_type == 2:
        target_time = release_time - pd.Timedelta(hours=rng.uniform(1.5, 3.0))
        target_speed = rng.uniform(10.0, 14.0)
    elif b_type == 3:
        target_lat += rng.uniform(0.04, 0.08) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.04, 0.08) * rng.choice([-1, 1])
        target_speed = 1.0
        loiter = True
    elif b_type == 4:
        target_lat += rng.uniform(-0.05, 0.05)
        target_lon += rng.uniform(-0.05, 0.05)
        target_speed = rng.uniform(11.0, 15.0)
    elif b_type == "DCY01":
        # Passes close to source at normal speed. No meaningful slowdown.
        target_lat += rng.uniform(0.01, 0.03) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.01, 0.03) * rng.choice([-1, 1])
        target_speed = rng.uniform(11.0, 15.0)
        fly_through = True
    elif b_type == "DCY02":
        # Approaches source and slows down, but minimum distance remains outside release tolerance.
        target_lat += rng.uniform(0.05, 0.08) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.05, 0.08) * rng.choice([-1, 1])
        target_speed = rng.uniform(2.0, 4.0)
        slowdown = True
    elif b_type == "DCY03":
        # Reaches source region but at the wrong time (e.g. 3 hours early).
        target_lat += rng.uniform(-0.01, 0.01)
        target_lon += rng.uniform(-0.01, 0.01)
        target_time = release_time - pd.Timedelta(hours=rng.uniform(2.5, 4.0))
        target_speed = rng.uniform(11.0, 15.0)
    elif b_type == "DCY04":
        # Loiters near source but does not have a valid approach pattern (e.g. starts and stays there).
        target_lat += rng.uniform(0.01, 0.02) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.01, 0.02) * rng.choice([-1, 1])
        target_speed = 1.0
        # Instead of using the complex loiter phase, we just make it drive extremely slowly (1 knot) the whole time
        # so it just crawls around the source area.
        loiter = False
        slowdown = False
        target_time = release_time
    elif b_type == "DCY05":
        # Approaches correctly but departs before actual release time.
        target_lat += rng.uniform(-0.01, 0.01)
        target_lon += rng.uniform(-0.01, 0.01)
        target_time = release_time - pd.Timedelta(hours=rng.uniform(1.0, 1.5))
        target_speed = rng.uniform(1.0, 2.0)
        slowdown = True
        early_departure = True
    else:
        target_lat += rng.uniform(0.08, 0.12) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.08, 0.12) * rng.choice([-1, 1])
        target_speed = 1.0
        slowdown = True
        loiter = True

    seconds_to_target = (target_time - start_time).total_seconds()
    approach_speed = 12.0 if slowdown or loiter else target_speed

    distance_km = (approach_speed * 1.852 * seconds_to_target) / 3600.0
    angle = rng.uniform(0, 360)
    bearing = (angle + 180) % 360

    angular_distance = distance_km / 6371.0088
    lat1 = math.radians(target_lat)
    lon1 = math.radians(target_lon)
    b_rad = math.radians(angle)
    lat2 = math.asin(math.sin(lat1) * math.cos(angular_distance) + math.cos(lat1) * math.sin(angular_distance) * math.cos(b_rad))
    lon2 = lon1 + math.atan2(math.sin(b_rad) * math.sin(angular_distance) * math.cos(lat1), math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2))

    current_lat = math.degrees(lat2)
    current_lon = math.degrees(lon2)
    current_time = start_time

    records = []

    while current_time <= end_time:
        course = bearing_between(current_lat, current_lon, target_lat, target_lon)
        minutes_from_target = (current_time - target_time).total_seconds() / 60.0

        if slowdown and -40 <= minutes_from_target <= 0:
            speed = max(target_speed, approach_speed - (approach_speed - target_speed) * (40 + minutes_from_target)/40.0)
        elif loiter and 0 < minutes_from_target <= 40:
            speed = max(0.5, rng.normal(1.0, 0.2))
            course = rng.uniform(0, 360)
        elif minutes_from_target > 0:
            speed = approach_speed
            course = bearing
        else:
            speed = approach_speed

        interval = sample_reporting_interval(rng, moving=(speed > 3.0))

        distance_to_target = haversine_km(current_lat, current_lon, target_lat, target_lon)
        max_dist = speed * 1.852 * interval / 3600.0

        if not fly_through and minutes_from_target <= 0 and max_dist >= distance_to_target:
            interval = max(1, int((target_time - current_time).total_seconds()))
            if interval > 0:
                speed = (distance_to_target * 3600.0) / (interval * 1.852)
            current_lat = target_lat
            current_lon = target_lon
            course = bearing
        else:
            current_lat, current_lon = move_vessel(current_lat, current_lon, course, speed, interval)

        add_record(
            records, vessel_id, current_time, current_lat, current_lon,
            speed + rng.normal(0, 0.15), course, course + rng.normal(0, 1),
            vessel_type, "UN", scenario.scenario_id
        )

        current_time += pd.Timedelta(seconds=interval)

    return pd.DataFrame(records)

# -------------------------------------------------------------------
# DATASET
# -------------------------------------------------------------------

def generate_scenario_dataset(
    config: SyntheticScenarioConfig,
) -> tuple[pd.DataFrame, dict]:

    rng = np.random.default_rng(
        config.seed
    )

    tracks = []

    # Background traffic.
    for i in range(
        config.num_background_vessels
    ):
        tracks.append(
            generate_background_vessel(
                config,
                i + 1,
                rng,
            )
        )

    # True source.
    tracks.append(
        generate_source_vessel(
            config,
            rng,
        )
    )

    # Decoys.
    for i in range(
        config.num_decoy_vessels
    ):
        tracks.append(
            generate_decoy_vessel(
                config,
                i,
                rng,
            )
        )

    df = pd.concat(
        tracks,
        ignore_index=True,
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    df = (
        df.sort_values(
            ["timestamp", "vessel_id"]
        )
        .drop_duplicates(
            subset=[
                "vessel_id",
                "timestamp",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    # Return string timestamps in the CSV.
    df["timestamp"] = df[
        "timestamp"
    ].map(iso_utc)

    ground_truth = {
        "scenario_id": config.scenario_id,
        "synthetic": True,

        "source": {
            "vessel_id": config.source_vessel_id,
            "latitude": config.release_lat,
            "longitude": config.release_lon,
            "timestamp": iso_utc(
                config.release_time
            ),
        },

        "observation": {
            "latitude": config.observation_lat,
            "longitude": config.observation_lon,
            "timestamp": iso_utc(
                config.observation_time
            ),
            "drift_duration_hours": (
                config.drift_duration_hours
            ),
        },

        "candidate_vessels": [
            config.source_vessel_id,
            *[
                f"{getattr(config, 'vessel_id_prefix', 'SYNTH-')}DCY{config.decoy_start_id + i:02d}"
                if config.scenario_id == "scenario-003"
                else f"{getattr(config, 'vessel_id_prefix', 'SYNTH-')}DCY{config.decoy_start_id + i:04d}"
                for i in range(
                    config.num_decoy_vessels
                )
            ],
        ],

        "expected_behavior": {
            "approach": True,
            "slowdown_near_source": True,
            "release_at_source": True,
            "brief_loiter": True,
            "departure_after_release": True,
        },
    }

    return df, ground_truth