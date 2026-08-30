from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.synthetic.ocean_mask import OceanMask
from scripts.synthetic.yearly_config import YearlyAISConfig


KNOTS_TO_MS = 0.51444
EARTH_RADIUS_M = 6_371_000.0


@dataclass
class VesselState:
    vessel_id: str
    vessel_type: str
    country: str
    latitude: float
    longitude: float
    course: float
    speed_knots: float
    interval_seconds: int


VESSEL_PROFILES = {
    "Cargo": {
        "speed_min": 6.0,
        "speed_max": 18.0,
        "intervals": [15, 30, 60, 120, 180, 300],
    },
    "Tanker": {
        "speed_min": 5.0,
        "speed_max": 15.0,
        "intervals": [15, 30, 60, 120, 180, 300],
    },
    "Passenger": {
        "speed_min": 8.0,
        "speed_max": 22.0,
        "intervals": [10, 15, 30, 60],
    },
    "Fishing": {
        "speed_min": 0.0,
        "speed_max": 12.0,
        "intervals": [30, 60, 120, 300, 600],
    },
    "Tug": {
        "speed_min": 0.0,
        "speed_max": 12.0,
        "intervals": [15, 30, 60, 120, 300],
    },
    "Pleasure Craft": {
        "speed_min": 0.0,
        "speed_max": 20.0,
        "intervals": [15, 30, 60, 120, 300],
    },
}


VESSEL_TYPE_PROBABILITIES = {
    "Cargo": 0.30,
    "Tanker": 0.25,
    "Passenger": 0.12,
    "Fishing": 0.15,
    "Tug": 0.08,
    "Pleasure Craft": 0.10,
}


COUNTRIES = [
    "GR",
    "CY",
    "MT",
    "IT",
    "TR",
    "EG",
    "PA",
    "LR",
]


def move_vessel(
    latitude: float,
    longitude: float,
    course_deg: float,
    speed_knots: float,
    seconds: float,
) -> tuple[float, float]:
    """
    Move a vessel over a spherical Earth.

    course_deg:
        0   = north
        90  = east
        180 = south
        270 = west
    """

    speed_ms = speed_knots * KNOTS_TO_MS
    course_rad = np.radians(course_deg)

    north_m = (
        speed_ms
        * np.cos(course_rad)
        * seconds
    )

    east_m = (
        speed_ms
        * np.sin(course_rad)
        * seconds
    )

    delta_lat = np.degrees(
        north_m / EARTH_RADIUS_M
    )

    cos_lat = np.cos(
        np.radians(latitude)
    )

    if abs(cos_lat) < 1e-8:
        return latitude, longitude

    delta_lon = np.degrees(
        east_m
        / (
            EARTH_RADIUS_M
            * cos_lat
        )
    )

    return (
        latitude + delta_lat,
        longitude + delta_lon,
    )


def choose_vessel_type(
    rng: np.random.Generator,
) -> str:
    names = list(
        VESSEL_TYPE_PROBABILITIES.keys()
    )

    probabilities = np.array(
        list(
            VESSEL_TYPE_PROBABILITIES.values()
        ),
        dtype=float,
    )

    return str(
        rng.choice(
            names,
            p=probabilities,
        )
    )


def create_fleet(
    config: YearlyAISConfig,
    rng: np.random.Generator,
    ocean_mask: OceanMask,
) -> list[VesselState]:
    """
    Create a persistent synthetic fleet.

    Initial positions are sampled only from valid ocean cells.
    """

    fleet: list[VesselState] = []

    for index in range(
        1,
        config.num_vessels + 1,
    ):
        vessel_type = choose_vessel_type(
            rng
        )

        profile = VESSEL_PROFILES[
            vessel_type
        ]

        latitude, longitude = (
            ocean_mask.sample_ocean_point(
                rng=rng,
                lat_min=config.region_min_lat,
                lat_max=config.region_max_lat,
                lon_min=config.region_min_lon,
                lon_max=config.region_max_lon,
            )
        )

        fleet.append(
            VesselState(
                vessel_id=(
                    f"SYNTH-Y2019-{index:06d}"
                ),
                vessel_type=vessel_type,
                country=str(
                    rng.choice(COUNTRIES)
                ),
                latitude=latitude,
                longitude=longitude,
                course=float(
                    rng.uniform(
                        0.0,
                        360.0,
                    )
                ),
                speed_knots=float(
                    rng.uniform(
                        profile["speed_min"],
                        profile["speed_max"],
                    )
                ),
                interval_seconds=int(
                    rng.choice(
                        profile["intervals"]
                    )
                ),
            )
        )

    return fleet


def apply_missing_values(
    row: dict,
    config: YearlyAISConfig,
    rng: np.random.Generator,
) -> None:
    """
    Apply configured missing-value probabilities only
    to optional AIS fields.
    """

    if (
        rng.random()
        < config.missing_heading_rate
    ):
        row["heading"] = np.nan

    if (
        rng.random()
        < config.missing_course_rate
    ):
        row["course"] = np.nan

    if (
        rng.random()
        < config.missing_speed_rate
    ):
        row["speed"] = np.nan


def choose_new_course(
    current_course: float,
    rng: np.random.Generator,
    turn_scale_deg: float = 3.0,
) -> float:
    """
    Add a small realistic course variation.
    """

    return (
        current_course
        + rng.normal(
            0.0,
            turn_scale_deg,
        )
    ) % 360.0


def choose_new_speed(
    current_speed: float,
    profile: dict,
    rng: np.random.Generator,
) -> float:
    """
    Apply a small speed variation while respecting
    vessel-type limits.
    """

    speed = (
        current_speed
        + rng.normal(
            0.0,
            0.25,
        )
    )

    return float(
        np.clip(
            speed,
            profile["speed_min"],
            profile["speed_max"],
        )
    )


def generate_vessel_track(
    vessel: VesselState,
    config: YearlyAISConfig,
    start_time: datetime,
    end_time: datetime,
    rng: np.random.Generator,
    ocean_mask: OceanMask,
) -> list[dict]:
    """
    Generate a continuous AIS trajectory.

    Both the initial position and every subsequent proposed
    position are checked against the ocean mask.

    If a proposed position would enter an invalid/land-like
    grid cell or leave the configured region, the vessel:

        1. stays at its current valid location
        2. reverses course

    It is never teleported.
    """

    records: list[dict] = []

    current_time = start_time

    profile = VESSEL_PROFILES[
        vessel.vessel_type
    ]

    while current_time <= end_time:

        # --------------------------------------------------
        # Update vessel behavior
        # --------------------------------------------------

        vessel.course = choose_new_course(
            vessel.course,
            rng,
        )

        vessel.speed_knots = choose_new_speed(
            vessel.speed_knots,
            profile,
            rng,
        )

        # --------------------------------------------------
        # AIS reporting value
        # --------------------------------------------------

        reported_speed = (
            vessel.speed_knots
        )

        # Occasional stationary/slow event.
        if rng.random() < 0.01:
            reported_speed = 0.0

        row = {
            "timestamp": (
                current_time.isoformat()
            ),
            "vessel_id": (
                vessel.vessel_id
            ),
            "longitude": round(
                vessel.longitude,
                6,
            ),
            "latitude": round(
                vessel.latitude,
                6,
            ),
            "speed": round(
                reported_speed,
                2,
            ),
            "course": round(
                vessel.course,
                2,
            ),
            "heading": round(
                vessel.course,
                2,
            ),
            "vessel_type": (
                vessel.vessel_type
            ),
            "country": vessel.country,
            "is_synthetic": True,
            "scenario_id": (
                "synthetic-2019"
            ),
        }

        apply_missing_values(
            row,
            config,
            rng,
        )

        records.append(row)

        # --------------------------------------------------
        # Choose next reporting interval
        # --------------------------------------------------

        next_interval = (
            vessel.interval_seconds
        )

        # Occasionally vary the reporting
        # interval within the vessel's profile.
        if rng.random() < 0.10:
            next_interval = int(
                rng.choice(
                    profile["intervals"]
                )
            )

        vessel.interval_seconds = (
            next_interval
        )

        # --------------------------------------------------
        # Calculate proposed next position
        # --------------------------------------------------

        new_latitude, new_longitude = (
            move_vessel(
                latitude=vessel.latitude,
                longitude=vessel.longitude,
                course_deg=vessel.course,
                speed_knots=reported_speed,
                seconds=next_interval,
            )
        )

        # --------------------------------------------------
        # Geographic bounds check
        # --------------------------------------------------

        inside_region = (
            config.region_min_lat
            <= new_latitude
            <= config.region_max_lat
            and
            config.region_min_lon
            <= new_longitude
            <= config.region_max_lon
        )

        # --------------------------------------------------
        # Ocean-mask check
        # --------------------------------------------------

        valid_ocean_position = False

        if inside_region:
            valid_ocean_position = (
                ocean_mask.is_ocean(
                    new_latitude,
                    new_longitude,
                )
            )

        # --------------------------------------------------
        # Accept or reject the movement
        # --------------------------------------------------

        if (
            inside_region
            and valid_ocean_position
        ):
            # Normal movement.
            vessel.latitude = (
                new_latitude
            )
            vessel.longitude = (
                new_longitude
            )

        else:
            # The proposed movement entered
            # land/invalid data or exited the region.
            #
            # IMPORTANT:
            # Never teleport the vessel.
            #
            # Keep the current valid position and
            # reverse its direction so future movement
            # heads back toward valid water.
            vessel.course = (
                vessel.course
                + 180.0
            ) % 360.0

        current_time += timedelta(
            seconds=next_interval
        )

    return records


def main() -> None:
    config = YearlyAISConfig()

    # ------------------------------------------------------
    # January 2019
    # ------------------------------------------------------

    start_time = datetime(
        config.year,
        1,
        1,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )

    end_time = (
        datetime(
            config.year,
            2,
            1,
            0,
            0,
            0,
            tzinfo=timezone.utc,
        )
        - timedelta(seconds=1)
    )

    rng = np.random.default_rng(
        config.seed
    )

    print("=" * 80)
    print(
        "JANUARY 2019 SYNTHETIC AIS GENERATION"
    )
    print("=" * 80)

    print(
        f"Vessels       : "
        f"{config.num_vessels}"
    )

    print(
        f"Period        : "
        f"{start_time} → {end_time}"
    )

    print(
        f"Region        : "
        f"{config.region_min_lat}–"
        f"{config.region_max_lat} N, "
        f"{config.region_min_lon}–"
        f"{config.region_max_lon} E"
    )

    print(
        f"Seed          : "
        f"{config.seed}"
    )

    print()

    # ------------------------------------------------------
    # Ocean mask
    # ------------------------------------------------------

    cmems_path = (
        PROJECT_ROOT
        / "data"
        / "ocean"
        / "raw"
        / "med_currents_2019-07-event.nc"
    )

    with OceanMask(
        cmems_path
    ) as ocean_mask:

        # --------------------------------------------------
        # Persistent fleet
        # --------------------------------------------------

        fleet = create_fleet(
            config=config,
            rng=rng,
            ocean_mask=ocean_mask,
        )

        records: list[dict] = []

        # --------------------------------------------------
        # Generate tracks
        # --------------------------------------------------

        for index, vessel in enumerate(
            fleet,
            start=1,
        ):

            records.extend(
                generate_vessel_track(
                    vessel=vessel,
                    config=config,
                    start_time=start_time,
                    end_time=end_time,
                    rng=rng,
                    ocean_mask=ocean_mask,
                )
            )

            if index % 25 == 0:
                print(
                    f"Generated "
                    f"{index}/"
                    f"{config.num_vessels} vessels..."
                )

    # ------------------------------------------------------
    # DataFrame
    # ------------------------------------------------------

    df = pd.DataFrame(
        records
    )

    df["timestamp"] = (
        pd.to_datetime(
            df["timestamp"],
            utc=True,
        )
    )

    df = (
        df.sort_values(
            [
                "vessel_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------
    # Output directory
    # ------------------------------------------------------

    output_dir = (
        PROJECT_ROOT
        / "data"
        / "ais"
        / "processed"
        / "yearly"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------
    # CSV
    # ------------------------------------------------------

    output_path = (
        output_dir
        / "synthetic_ais_2019_01.csv"
    )

    df.to_csv(
        output_path,
        index=False,
    )

    # ------------------------------------------------------
    # Manifest
    # ------------------------------------------------------

    manifest = {
        "year": config.year,
        "month": 1,
        "seed": config.seed,
        "vessel_count": int(
            df["vessel_id"]
            .nunique()
        ),
        "record_count": int(
            len(df)
        ),
        "start_time": (
            df["timestamp"]
            .min()
            .isoformat()
        ),
        "end_time": (
            df["timestamp"]
            .max()
            .isoformat()
        ),
        "region": {
            "latitude_min": (
                config.region_min_lat
            ),
            "latitude_max": (
                config.region_max_lat
            ),
            "longitude_min": (
                config.region_min_lon
            ),
            "longitude_max": (
                config.region_max_lon
            ),
        },
        "scenario_id": (
            "synthetic-2019"
        ),
        "is_synthetic": True,
        "missing_heading_rate": (
            config.missing_heading_rate
        ),
        "missing_course_rate": (
            config.missing_course_rate
        ),
        "missing_speed_rate": (
            config.missing_speed_rate
        ),
    }

    manifest_path = (
        output_dir
        / "synthetic_ais_2019_01_manifest.json"
    )

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
        )

    # ------------------------------------------------------
    # Final output
    # ------------------------------------------------------

    print()
    print("=" * 80)
    print("GENERATION COMPLETE")
    print("=" * 80)

    print(
        f"Records       : "
        f"{len(df):,}"
    )

    print(
        f"Vessels       : "
        f"{df['vessel_id'].nunique():,}"
    )

    print(
        f"Output        : "
        f"{output_path}"
    )

    print(
        f"Manifest      : "
        f"{manifest_path}"
    )


if __name__ == "__main__":
    main()