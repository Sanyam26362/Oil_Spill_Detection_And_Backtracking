import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


FILE = Path(
    "data/ais/raw/piraeus/dynamic/unipi_ais_dynamic_jan2019.csv"
)

# Number of rows to inspect.
# Increase later if needed.
MAX_ROWS = 1_000_000


def to_datetime(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    )


def haversine_km(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """
    Calculate great-circle distance between two geographic points.
    Result is in kilometers.
    """
    earth_radius_km = 6371.0088

    lon1_rad = math.radians(lon1)
    lat1_rad = math.radians(lat1)
    lon2_rad = math.radians(lon2)
    lat2_rad = math.radians(lat2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * earth_radius_km * math.asin(math.sqrt(a))


total_rows = 0
vessels = set()

speeds = []
courses = []
headings = []

missing_speed = 0
missing_course = 0
missing_heading = 0
invalid_coordinates = 0

min_lon = float("inf")
max_lon = float("-inf")
min_lat = float("inf")
max_lat = float("-inf")

min_timestamp = None
max_timestamp = None

# For a small number of vessels, track consecutive observations.
# This helps us understand real trajectory behavior.
previous = {}

time_gaps_seconds = []
distances_km = []
speed_changes = []
course_changes = []

MAX_TRAJECTORY_VESSELS = 500
trajectory_vessels = set()


with FILE.open(
    "r",
    encoding="utf-8",
    newline="",
) as file:

    reader = csv.DictReader(file)

    for row in reader:

        total_rows += 1

        if total_rows > MAX_ROWS:
            break

        vessel_id = row["vessel_id"]
        vessels.add(vessel_id)

        timestamp_ms = int(row["t"])

        if min_timestamp is None or timestamp_ms < min_timestamp:
            min_timestamp = timestamp_ms

        if max_timestamp is None or timestamp_ms > max_timestamp:
            max_timestamp = timestamp_ms

        # -----------------------------
        # Coordinates
        # -----------------------------

        try:
            lon = float(row["lon"])
            lat = float(row["lat"])

            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                invalid_coordinates += 1
                continue

        except (TypeError, ValueError):
            invalid_coordinates += 1
            continue

        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)

        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)

        # -----------------------------
        # Speed
        # -----------------------------

        current_speed = None

        if row["speed"] not in ("", None):
            try:
                current_speed = float(row["speed"])
                speeds.append(current_speed)
            except ValueError:
                missing_speed += 1
        else:
            missing_speed += 1

        # -----------------------------
        # Course
        # -----------------------------

        current_course = None

        if row["course"] not in ("", None):
            try:
                current_course = float(row["course"])
                courses.append(current_course)
            except ValueError:
                missing_course += 1
        else:
            missing_course += 1

        # -----------------------------
        # Heading
        # -----------------------------

        current_heading = None

        if row["heading"] not in ("", None):
            try:
                current_heading = float(row["heading"])
                headings.append(current_heading)
            except ValueError:
                missing_heading += 1
        else:
            missing_heading += 1

        # -----------------------------
        # Consecutive trajectory data
        # -----------------------------

        if (
            vessel_id in previous
            and len(trajectory_vessels) < MAX_TRAJECTORY_VESSELS
        ):

            trajectory_vessels.add(vessel_id)

            previous_timestamp, previous_lon, previous_lat, previous_speed, previous_course = previous[
                vessel_id
            ]

            gap_seconds = (
                timestamp_ms - previous_timestamp
            ) / 1000

            # Only use sensible positive time gaps.
            if gap_seconds > 0:
                time_gaps_seconds.append(gap_seconds)

                distance = haversine_km(
                    previous_lon,
                    previous_lat,
                    lon,
                    lat,
                )

                distances_km.append(distance)

                if (
                    current_speed is not None
                    and previous_speed is not None
                ):
                    speed_changes.append(
                        abs(current_speed - previous_speed)
                    )

                if (
                    current_course is not None
                    and previous_course is not None
                ):
                    # Circular difference:
                    # 359° → 1° is a 2° change, not 358°.
                    course_difference = abs(
                        current_course - previous_course
                    )

                    course_difference = min(
                        course_difference,
                        360 - course_difference,
                    )

                    course_changes.append(
                        course_difference
                    )

        previous[vessel_id] = (
            timestamp_ms,
            lon,
            lat,
            current_speed,
            current_course,
        )


print("\n========== PIRAEUS AIS ANALYSIS ==========\n")

print(f"Rows inspected: {total_rows:,}")
print(f"Unique vessels in sample: {len(vessels):,}")

print("\n--- TIME ---")

if min_timestamp is not None:
    print("Start:", to_datetime(min_timestamp).isoformat())
    print("End:  ", to_datetime(max_timestamp).isoformat())

print("\n--- GEOGRAPHY ---")
print(f"Longitude: {min_lon:.6f} → {max_lon:.6f}")
print(f"Latitude:  {min_lat:.6f} → {max_lat:.6f}")

print("\n--- SPEED ---")

if speeds:
    print(f"Valid values: {len(speeds):,}")
    print(f"Minimum: {min(speeds):.3f}")
    print(f"Maximum: {max(speeds):.3f}")
    print(f"Mean: {statistics.mean(speeds):.3f}")
    print(f"Median: {statistics.median(speeds):.3f}")

print(f"Missing/invalid: {missing_speed:,}")

print("\n--- COURSE ---")

if courses:
    print(f"Valid values: {len(courses):,}")
    print(f"Minimum: {min(courses):.3f}")
    print(f"Maximum: {max(courses):.3f}")
    print(f"Mean: {statistics.mean(courses):.3f}")

print(f"Missing/invalid: {missing_course:,}")

print("\n--- HEADING ---")

if headings:
    print(f"Valid values: {len(headings):,}")
    print(f"Minimum: {min(headings):.3f}")
    print(f"Maximum: {max(headings):.3f}")

print(f"Missing/invalid: {missing_heading:,}")

print("\n--- TRAJECTORY BEHAVIOR ---")

if time_gaps_seconds:
    print(
        "Median reporting gap (seconds):",
        f"{statistics.median(time_gaps_seconds):.3f}",
    )

    print(
        "Mean reporting gap (seconds):",
        f"{statistics.mean(time_gaps_seconds):.3f}",
    )

if distances_km:
    print(
        "Median distance between consecutive observations (km):",
        f"{statistics.median(distances_km):.6f}",
    )

if speed_changes:
    print(
        "Median absolute speed change:",
        f"{statistics.median(speed_changes):.3f}",
    )

if course_changes:
    print(
        "Median course change:",
        f"{statistics.median(course_changes):.3f}",
    )

print("\n--- QUALITY ---")
print(f"Invalid coordinates: {invalid_coordinates:,}")

print("\n==========================================\n")