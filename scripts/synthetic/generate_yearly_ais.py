from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.synthetic.ocean_mask import OceanMask
from scripts.synthetic.yearly_config import YearlyAISConfig


# ============================================================
# CONSTANTS
# ============================================================

KNOTS_TO_MS = 0.51444
EARTH_RADIUS_M = 6_371_000.0

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "ais"
    / "processed"
    / "yearly"
)

CMEMS_PATH = (
    PROJECT_ROOT
    / "data"
    / "ocean"
    / "raw"
    / "yearly"
)

# We deliberately start with January-June.
# Change this to 12 only after the half-year run passes validation.
START_MONTH = 7
END_MONTH = 12


# ============================================================
# VESSEL STATE
# ============================================================

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
    next_report_time: str


# ============================================================
# VESSEL PROFILES
# ============================================================

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


# ============================================================
# MOVEMENT
# ============================================================

def move_vessel(
    latitude: float,
    longitude: float,
    course_deg: float,
    speed_knots: float,
    seconds: float,
) -> tuple[float, float]:
    """Move a vessel over a spherical Earth."""

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


# ============================================================
# RANDOM BEHAVIOR
# ============================================================

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


def choose_course(
    current_course: float,
    rng: np.random.Generator,
) -> float:
    return (
        current_course
        + rng.normal(
            0.0,
            3.0,
        )
    ) % 360.0


def choose_speed(
    current_speed: float,
    profile: dict,
    rng: np.random.Generator,
) -> float:
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


def choose_interval(
    current_interval: int,
    profile: dict,
    rng: np.random.Generator,
) -> int:
    if rng.random() < 0.10:
        return int(
            rng.choice(
                profile["intervals"]
            )
        )

    return current_interval


# ============================================================
# MISSING VALUES
# ============================================================

def apply_missing_values(
    row: dict,
    config: YearlyAISConfig,
    rng: np.random.Generator,
) -> None:

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


# ============================================================
# FLEET CREATION
# ============================================================

def create_initial_fleet(
    config: YearlyAISConfig,
    rng: np.random.Generator,
    ocean_mask: OceanMask,
) -> list[VesselState]:

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
                next_report_time=month_start(config.year, 1).isoformat(),
            )
        )

    return fleet


# ============================================================
# SINGLE VESSEL MONTH
# ============================================================

def generate_vessel_month(
    vessel: VesselState,
    config: YearlyAISConfig,
    start_time: datetime,
    end_time: datetime,
    rng: np.random.Generator,
    ocean_mask: OceanMask,
) -> list[dict]:

    records: list[dict] = []

    current_time = datetime.fromisoformat(vessel.next_report_time)

    profile = VESSEL_PROFILES[
        vessel.vessel_type
    ]

    while current_time <= end_time:

        # ----------------------------------------------------
        # Update behavior
        # ----------------------------------------------------

        vessel.course = choose_course(
            vessel.course,
            rng,
        )

        vessel.speed_knots = choose_speed(
            vessel.speed_knots,
            profile,
            rng,
        )

        reported_speed = (
            vessel.speed_knots
        )

        # Small probability of a stationary point.
        if rng.random() < 0.01:
            reported_speed = 0.0

        # ----------------------------------------------------
        # Record current state
        # ----------------------------------------------------

        row = {
            "timestamp": (
                current_time.isoformat()
            ),
            "vessel_id": vessel.vessel_id,
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
            "vessel_type": vessel.vessel_type,
            "country": vessel.country,
            "is_synthetic": True,
            "scenario_id": "synthetic-2019",
        }

        apply_missing_values(
            row,
            config,
            rng,
        )

        records.append(row)

        # ----------------------------------------------------
        # Reporting interval
        # ----------------------------------------------------

        next_interval = choose_interval(
            vessel.interval_seconds,
            profile,
            rng,
        )

        vessel.interval_seconds = (
            next_interval
        )

        # ----------------------------------------------------
        # Proposed movement
        # ----------------------------------------------------

        new_latitude, new_longitude = (
            move_vessel(
                latitude=vessel.latitude,
                longitude=vessel.longitude,
                course_deg=vessel.course,
                speed_knots=reported_speed,
                seconds=next_interval,
            )
        )

        # ----------------------------------------------------
        # Region check
        # ----------------------------------------------------

        inside_region = (
            config.region_min_lat
            <= new_latitude
            <= config.region_max_lat
            and
            config.region_min_lon
            <= new_longitude
            <= config.region_max_lon
        )

        # ----------------------------------------------------
        # Ocean check
        # ----------------------------------------------------

        valid_ocean = False

        if inside_region:
            valid_ocean = (
                ocean_mask.is_ocean(
                    new_latitude,
                    new_longitude,
                )
            )

        # ----------------------------------------------------
        # Accept movement or bounce
        # ----------------------------------------------------

        if (
            inside_region
            and valid_ocean
        ):
            vessel.latitude = new_latitude
            vessel.longitude = new_longitude

        else:
            # Never teleport.
            vessel.course = (
                vessel.course + 180.0
            ) % 360.0

        current_time += timedelta(
            seconds=next_interval
        )
        
    vessel.next_report_time = current_time.isoformat()

    return records


# ============================================================
# MONTH HELPERS
# ============================================================

def month_start(
    year: int,
    month: int,
) -> datetime:
    return datetime(
        year,
        month,
        1,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )


def next_month_start(
    year: int,
    month: int,
) -> datetime:

    if month == 12:
        return datetime(
            year + 1,
            1,
            1,
            0,
            0,
            0,
            tzinfo=timezone.utc,
        )

    return datetime(
        year,
        month + 1,
        1,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )


# ============================================================
# MANIFEST
# ============================================================

def build_month_manifest(
    df: pd.DataFrame,
    year: int,
    month: int,
) -> dict:

    return {
        "year": year,
        "month": month,
        "vessel_count": int(
            df["vessel_id"].nunique()
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
        "scenario_id": "synthetic-2019",
        "is_synthetic": True,
    }


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    config = YearlyAISConfig()

    rng = np.random.default_rng(
        config.seed
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 80)
    print(
        "2019 SYNTHETIC AIS GENERATION"
    )
    print("=" * 80)

    print(
        f"Vessels          : "
        f"{config.num_vessels}"
    )

    print(
        f"Months           : "
        f"{START_MONTH} -> {END_MONTH}"
    )

    print(
        f"Seed             : "
        f"{config.seed}"
    )

    print()

    # --------------------------------------------------------
    # Ocean mask
    # --------------------------------------------------------

    with OceanMask(
        CMEMS_PATH
        / "med_currents_2019-07.nc"
    ) as ocean_mask:

        # ----------------------------------------------------
        # Create or load persistent fleet
        # ----------------------------------------------------

        if START_MONTH == 1:
            fleet = create_initial_fleet(
                config=config,
                rng=rng,
                ocean_mask=ocean_mask,
            )
        else:
            state_path = (
                OUTPUT_DIR
                / (
                    f"synthetic_ais_"
                    f"{config.year}_"
                    f"fleet_state_after_"
                    f"{START_MONTH - 1:02d}.json"
                )
            )
            print(f"Loading fleet state from {state_path}")
            with state_path.open("r", encoding="utf-8") as f:
                state_data = json.load(f)
            fleet = [VesselState(**d) for d in state_data]

        # ----------------------------------------------------
        # Generate each month sequentially.
        #
        # VesselState is deliberately NOT reset.
        # ----------------------------------------------------

        for month in range(
            START_MONTH,
            END_MONTH + 1,
        ):

            start = month_start(
                config.year,
                month,
            )

            end = (
                next_month_start(
                    config.year,
                    month,
                )
                - timedelta(
                    seconds=1
                )
            )

            print()
            print(
                "-" * 80
            )

            print(
                f"Generating "
                f"{config.year}-{month:02d}"
            )

            month_records: list[dict] = []

            for index, vessel in enumerate(
                fleet,
                start=1,
            ):

                month_records.extend(
                    generate_vessel_month(
                        vessel=vessel,
                        config=config,
                        start_time=start,
                        end_time=end,
                        rng=rng,
                        ocean_mask=ocean_mask,
                    )
                )

                if index % 25 == 0:
                    print(
                        f"  vessels: "
                        f"{index}/"
                        f"{config.num_vessels}"
                    )

            df = pd.DataFrame(
                month_records
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

            output_path = (
                OUTPUT_DIR
                / (
                    f"synthetic_ais_"
                    f"{config.year}-"
                    f"{month:02d}.csv"
                )
            )

            df.to_csv(
                output_path,
                index=False,
            )

            manifest = build_month_manifest(
                df,
                config.year,
                month,
            )

            manifest_path = (
                OUTPUT_DIR
                / (
                    f"synthetic_ais_"
                    f"{config.year}-"
                    f"{month:02d}"
                    "_manifest.json"
                )
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

            print(
                f"  records : "
                f"{len(df):,}"
            )

            print(
                f"  vessels : "
                f"{df['vessel_id'].nunique():,}"
            )

            print(
                f"  output  : "
                f"{output_path}"
            )

            print(
                f"  state after month: "
                f"{fleet[0].vessel_id} "
                f"at "
                f"({fleet[0].latitude:.6f}, "
                f"{fleet[0].longitude:.6f})"
            )

    # --------------------------------------------------------
    # Save final fleet state for continuity checks/resume
    # --------------------------------------------------------

    state_path = (
        OUTPUT_DIR
        / (
            f"synthetic_ais_"
            f"{config.year}_"
            f"fleet_state_after_"
            f"{END_MONTH:02d}.json"
        )
    )

    state_data = [
        asdict(vessel)
        for vessel in fleet
    ]

    with state_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state_data,
            f,
            indent=2,
        )

    print()
    print("=" * 80)
    print("GENERATION COMPLETE")
    print("=" * 80)

    print(
        f"Generated months: "
        f"{START_MONTH} -> {END_MONTH}"
    )

    print(
        f"Final fleet state: "
        f"{state_path}"
    )


if __name__ == "__main__":
    main()