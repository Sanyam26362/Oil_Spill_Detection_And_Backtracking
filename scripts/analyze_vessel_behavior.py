import csv
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone


DYNAMIC_FILE = Path(
    "data/ais/raw/piraeus/dynamic/unipi_ais_dynamic_jan2019.csv"
)

STATIC_FILE = Path(
    "data/ais/raw/piraeus/static/ais_static/unipi_ais_static.csv"
)

CODE_FILE = Path(
    "data/ais/raw/piraeus/static/ais_static/ais_codes_descriptions.csv"
)

# Maximum number of values retained for approximate percentile calculations.
# This prevents the analysis from consuming huge amounts of RAM.
RESERVOIR_SIZE = 20_000

# Only use consecutive observations with gaps <= this value when measuring
# local speed/course behavior. Large gaps are useful for reporting-gap
# analysis, but they can distort acceleration/course-change statistics.
MAX_BEHAVIOR_GAP_SECONDS = 300

# Speed above this is flagged as an extreme value for inspection.
EXTREME_SPEED_KNOTS = 50.0


# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

def circular_difference(a: float, b: float) -> float:
    """Return the smallest angular difference between two angles."""
    diff = abs(a - b)
    return min(diff, 360.0 - diff)


def haversine_km(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """Great-circle distance between two WGS84 points in kilometres."""
    earth_radius_km = 6371.0088

    lon1 = math.radians(lon1)
    lat1 = math.radians(lat1)
    lon2 = math.radians(lon2)
    lat2 = math.radians(lat2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def reservoir_add(
    reservoir: list[float],
    value: float,
    seen_count: int,
) -> None:
    """
    Reservoir sampling.

    Keeps a representative sample while processing an arbitrarily
    large stream of values.
    """
    if len(reservoir) < RESERVOIR_SIZE:
        reservoir.append(value)
        return

    index = random.randint(0, seen_count - 1)

    if index < RESERVOIR_SIZE:
        reservoir[index] = value


def percentile(
    values: list[float],
    p: float,
) -> float | None:
    if not values:
        return None

    values = sorted(values)

    index = int((len(values) - 1) * p)

    return values[index]


def safe_mean(values: list[float]) -> float | None:
    if not values:
        return None

    return statistics.mean(values)


def type_family(shiptype: int | None) -> str:
    """
    Convert numeric AIS ship type into a broad vessel family.

    The actual numeric code is retained separately.
    """

    if shiptype is None:
        return "Unknown"

    if shiptype == 30:
        return "Fishing"

    if 31 <= shiptype <= 39:
        if shiptype == 36:
            return "Sailing"
        if shiptype == 37:
            return "Pleasure Craft"
        return "Special/Other 30s"

    if 40 <= shiptype <= 49:
        return "High Speed Craft"

    if 50 <= shiptype <= 59:
        return "Special Service"

    if 60 <= shiptype <= 69:
        return "Passenger"

    if 70 <= shiptype <= 79:
        return "Cargo"

    if 80 <= shiptype <= 89:
        return "Tanker"

    if 90 <= shiptype <= 99:
        return "Other"

    return "Unknown/Invalid"


def format_number(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "N/A"

    return f"{value:.{digits}f}"


# ------------------------------------------------------------
# Load AIS vessel type descriptions
# ------------------------------------------------------------

shiptype_descriptions: dict[int, str] = {}

with CODE_FILE.open(
    "r",
    encoding="utf-8",
    newline="",
) as file:

    reader = csv.DictReader(file)

    for row in reader:
        try:
            code = int(row["Type Code"])
        except (TypeError, ValueError):
            continue

        shiptype_descriptions[code] = row["Description"]


# ------------------------------------------------------------
# Load static vessel metadata
# ------------------------------------------------------------

vessel_metadata: dict[str, dict] = {}

invalid_shiptypes = Counter()
missing_shiptype_vessels = 0

with STATIC_FILE.open(
    "r",
    encoding="utf-8",
    newline="",
) as file:

    reader = csv.DictReader(file)

    for row in reader:

        vessel_id = row["vessel_id"]

        raw_shiptype = row.get("shiptype", "")

        shiptype = None

        if raw_shiptype:
            try:
                shiptype = int(float(raw_shiptype))

                if not 0 <= shiptype <= 99:
                    invalid_shiptypes[shiptype] += 1

            except ValueError:
                shiptype = None

        if shiptype is None:
            missing_shiptype_vessels += 1

        vessel_metadata[vessel_id] = {
            "country": row.get("country") or None,
            "shiptype": shiptype,
        }


# ------------------------------------------------------------
# Streaming statistics
# ------------------------------------------------------------

vessel_observations = Counter()
vessel_stationary = Counter()
vessel_moving = Counter()

# Counts by broad vessel family.
family_vessels: defaultdict[str, set[str]] = defaultdict(set)

# Samples for percentile estimation.
family_speed_samples: defaultdict[str, list[float]] = defaultdict(list)
family_moving_speed_samples: defaultdict[str, list[float]] = defaultdict(list)

family_gap_samples: defaultdict[str, list[float]] = defaultdict(list)
family_speed_change_samples: defaultdict[str, list[float]] = defaultdict(list)
family_course_change_samples: defaultdict[str, list[float]] = defaultdict(list)

# How many values have been seen by reservoir sampler.
family_speed_seen = Counter()
family_moving_speed_seen = Counter()
family_gap_seen = Counter()
family_speed_change_seen = Counter()
family_course_change_seen = Counter()

extreme_speed_by_family = Counter()

previous: dict[
    str,
    tuple[int, float, float, float | None, float | None],
] = {}

total_records = 0

global_min_timestamp = None
global_max_timestamp = None


# ------------------------------------------------------------
# Process dynamic AIS file
# ------------------------------------------------------------

print()
print("Reading:")
print(DYNAMIC_FILE)
print()
print("This may take a while because the January file contains millions")
print("of AIS records. The file is processed row-by-row; it is not")
print("loaded completely into RAM.")
print()

with DYNAMIC_FILE.open(
    "r",
    encoding="utf-8",
    newline="",
) as file:

    reader = csv.DictReader(file)

    for row in reader:

        total_records += 1

        vessel_id = row["vessel_id"]

        # -----------------------------
        # Timestamp
        # -----------------------------

        try:
            timestamp_ms = int(row["t"])
        except (TypeError, ValueError):
            continue

        if (
            global_min_timestamp is None
            or timestamp_ms < global_min_timestamp
        ):
            global_min_timestamp = timestamp_ms

        if (
            global_max_timestamp is None
            or timestamp_ms > global_max_timestamp
        ):
            global_max_timestamp = timestamp_ms

        # -----------------------------
        # Coordinates
        # -----------------------------

        try:
            lon = float(row["lon"])
            lat = float(row["lat"])
        except (TypeError, ValueError):
            continue

        if not (-180 <= lon <= 180):
            continue

        if not (-90 <= lat <= 90):
            continue

        # -----------------------------
        # Speed
        # -----------------------------

        speed = None

        if row["speed"]:
            try:
                speed = float(row["speed"])
            except ValueError:
                speed = None

        # -----------------------------
        # Course
        # -----------------------------

        course = None

        if row["course"]:
            try:
                course = float(row["course"])
            except ValueError:
                course = None

        # -----------------------------
        # Vessel type
        # -----------------------------

        metadata = vessel_metadata.get(vessel_id)

        shiptype = (
            metadata["shiptype"]
            if metadata
            else None
        )

        family = type_family(shiptype)

        family_vessels[family].add(vessel_id)
        vessel_observations[vessel_id] += 1

        # -----------------------------
        # Speed state
        # -----------------------------

        if speed is not None:

            family_speed_seen[family] += 1

            reservoir_add(
                family_speed_samples[family],
                speed,
                family_speed_seen[family],
            )

            if speed == 0:
                vessel_stationary[vessel_id] += 1

            else:
                vessel_moving[vessel_id] += 1

                family_moving_speed_seen[family] += 1

                reservoir_add(
                    family_moving_speed_samples[family],
                    speed,
                    family_moving_speed_seen[family],
                )

            if speed > EXTREME_SPEED_KNOTS:
                extreme_speed_by_family[family] += 1

        # -----------------------------
        # Compare with previous vessel
        # -----------------------------

        if vessel_id in previous:

            (
                previous_time,
                previous_lon,
                previous_lat,
                previous_speed,
                previous_course,
            ) = previous[vessel_id]

            gap_seconds = (
                timestamp_ms - previous_time
            ) / 1000.0

            # Reporting gaps are recorded regardless of size.
            if gap_seconds > 0:

                family_gap_seen[family] += 1

                reservoir_add(
                    family_gap_samples[family],
                    gap_seconds,
                    family_gap_seen[family],
                )

                # Only use short enough intervals to understand
                # local behavior.
                if gap_seconds <= MAX_BEHAVIOR_GAP_SECONDS:

                    if (
                        speed is not None
                        and previous_speed is not None
                    ):

                        change = abs(
                            speed - previous_speed
                        )

                        family_speed_change_seen[family] += 1

                        reservoir_add(
                            family_speed_change_samples[family],
                            change,
                            family_speed_change_seen[family],
                        )

                    if (
                        course is not None
                        and previous_course is not None
                    ):

                        change = circular_difference(
                            course,
                            previous_course,
                        )

                        family_course_change_seen[family] += 1

                        reservoir_add(
                            family_course_change_samples[family],
                            change,
                            family_course_change_seen[family],
                        )

        # Store current observation as previous.
        previous[vessel_id] = (
            timestamp_ms,
            lon,
            lat,
            speed,
            course,
        )

        # Simple progress indicator.
        if total_records % 1_000_000 == 0:
            print(
                f"Processed {total_records:,} records..."
            )


# ------------------------------------------------------------
# Global time range
# ------------------------------------------------------------

start_dt = (
    datetime.fromtimestamp(
        global_min_timestamp / 1000,
        tz=timezone.utc,
    )
    if global_min_timestamp is not None
    else None
)

end_dt = (
    datetime.fromtimestamp(
        global_max_timestamp / 1000,
        tz=timezone.utc,
    )
    if global_max_timestamp is not None
    else None
)


# ------------------------------------------------------------
# Final report
# ------------------------------------------------------------

print()
print("=" * 80)
print("              PIRAEUS AIS BEHAVIOR PROFILE")
print("=" * 80)

print()
print("DATASET")
print("-" * 80)
print(f"Records processed: {total_records:,}")
print(f"Unique vessels:    {len(vessel_observations):,}")

if start_dt and end_dt:
    print(f"Start UTC:         {start_dt.isoformat()}")
    print(f"End UTC:           {end_dt.isoformat()}")

print()
print("VESSEL TYPE PROFILE")
print("-" * 80)

for family in sorted(
    family_vessels,
    key=lambda x: len(family_vessels[x]),
    reverse=True,
):

    vessels = len(family_vessels[family])

    print(
        f"{family:22s} "
        f"vessels={vessels:4d}"
    )


print()
print("BEHAVIOR BY VESSEL FAMILY")
print("-" * 80)

families = sorted(
    family_vessels,
    key=lambda x: len(family_vessels[x]),
    reverse=True,
)

for family in families:

    print()
    print(f"[{family}]")

    vessels = family_vessels[family]

    total_obs = sum(
        vessel_observations[v]
        for v in vessels
    )

    stationary = sum(
        vessel_stationary[v]
        for v in vessels
    )

    moving = sum(
        vessel_moving[v]
        for v in vessels
    )

    stationary_pct = (
        stationary / (stationary + moving) * 100
        if stationary + moving > 0
        else 0
    )

    print(
        f"Vessels: {len(vessels)}"
    )

    print(
        f"Observations: {total_obs:,}"
    )

    print(
        f"Stationary records: "
        f"{stationary:,} "
        f"({stationary_pct:.2f}%)"
    )

    print(
        f"Moving records: "
        f"{moving:,}"
    )

    speeds = family_speed_samples[family]
    moving_speeds = family_moving_speed_samples[family]

    print()
    print("Speed (knots):")

    print(
        f"  median: "
        f"{format_number(percentile(speeds, 0.50))}"
    )

    print(
        f"  p75:    "
        f"{format_number(percentile(speeds, 0.75))}"
    )

    print(
        f"  p90:    "
        f"{format_number(percentile(speeds, 0.90))}"
    )

    print(
        f"  p95:    "
        f"{format_number(percentile(speeds, 0.95))}"
    )

    print(
        f"  p99:    "
        f"{format_number(percentile(speeds, 0.99))}"
    )

    print(
        f"  max sampled: "
        f"{format_number(max(speeds) if speeds else None)}"
    )

    print()
    print("Moving speed only (speed > 0):")

    print(
        f"  median: "
        f"{format_number(percentile(moving_speeds, 0.50))}"
    )

    print(
        f"  p90:    "
        f"{format_number(percentile(moving_speeds, 0.90))}"
    )

    print(
        f"  p95:    "
        f"{format_number(percentile(moving_speeds, 0.95))}"
    )

    print(
        f"  p99:    "
        f"{format_number(percentile(moving_speeds, 0.99))}"
    )

    print()
    print("Reporting gap (seconds):")

    gaps = family_gap_samples[family]

    print(
        f"  median: "
        f"{format_number(percentile(gaps, 0.50))}"
    )

    print(
        f"  p75:    "
        f"{format_number(percentile(gaps, 0.75))}"
    )

    print(
        f"  p90:    "
        f"{format_number(percentile(gaps, 0.90))}"
    )

    print(
        f"  p95:    "
        f"{format_number(percentile(gaps, 0.95))}"
    )

    print(
        f"  p99:    "
        f"{format_number(percentile(gaps, 0.99))}"
    )

    speed_changes_for_family = (
        family_speed_change_samples[family]
    )

    course_changes_for_family = (
        family_course_change_samples[family]
    )

    print()
    print(
        f"Speed change "
        f"(only gaps <= {MAX_BEHAVIOR_GAP_SECONDS}s):"
    )

    print(
        f"  median: "
        f"{format_number(percentile(speed_changes_for_family, 0.50))}"
    )

    print(
        f"  p90:    "
        f"{format_number(percentile(speed_changes_for_family, 0.90))}"
    )

    print(
        f"  p95:    "
        f"{format_number(percentile(speed_changes_for_family, 0.95))}"
    )

    print(
        f"  p99:    "
        f"{format_number(percentile(speed_changes_for_family, 0.99))}"
    )

    print()
    print(
        f"Course change "
        f"(only gaps <= {MAX_BEHAVIOR_GAP_SECONDS}s):"
    )

    print(
        f"  median: "
        f"{format_number(percentile(course_changes_for_family, 0.50))}"
    )

    print(
        f"  p90:    "
        f"{format_number(percentile(course_changes_for_family, 0.90))}"
    )

    print(
        f"  p95:    "
        f"{format_number(percentile(course_changes_for_family, 0.95))}"
    )

    print(
        f"  p99:    "
        f"{format_number(percentile(course_changes_for_family, 0.99))}"
    )

    print()
    print(
        f"Extreme speeds > {EXTREME_SPEED_KNOTS} knots: "
        f"{extreme_speed_by_family[family]:,}"
    )


print()
print("STATIC DATA QUALITY")
print("-" * 80)

print(
    f"Vessels with missing/invalid shiptype: "
    f"{missing_shiptype_vessels}"
)

print("Out-of-range ship types:")

if invalid_shiptypes:

    for shiptype, count in sorted(
        invalid_shiptypes.items()
    ):
        print(
            f"  {shiptype}: {count} vessel(s)"
        )

else:
    print("  None")


print()
print("=" * 80)
print("                    END OF REPORT")
print("=" * 80)
print()