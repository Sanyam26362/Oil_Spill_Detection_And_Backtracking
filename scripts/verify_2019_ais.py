from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

AIS_DIR = PROJECT_ROOT / "data" / "ais" / "processed" / "yearly"
REPORT_DIR = PROJECT_ROOT / "docs"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

JSON_REPORT = REPORT_DIR / "ais_2019_verification.json"
MD_REPORT = REPORT_DIR / "ais_2019_verification_report.md"

# Full synthetic AIS operating region
MIN_LAT = 30.5
MAX_LAT = 36.5
MIN_LON = 23.0
MAX_LON = 35.75

EXPECTED_START = datetime(
    2019, 1, 1, 0, 0, 0, tzinfo=timezone.utc
)

EXPECTED_END = datetime(
    2019, 12, 31, 23, 59, 59, tzinfo=timezone.utc
)

# Adjust if your generator uses a different interval.
EXPECTED_MONTHS = 12


# ============================================================
# HELPERS
# ============================================================

def parse_float(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_datetime(value):
    if not value:
        return None

    value = value.strip()

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except ValueError:
        return None


def normalize_header(header):
    return header.strip().lower()


def find_column(headers, candidates):
    normalized = {
        normalize_header(h): h
        for h in headers
    }

    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]

    return None


def month_key(dt):
    return dt.strftime("%Y-%m")


def is_finite_number(value):
    return value is not None and math.isfinite(value)


# ============================================================
# FILE DISCOVERY
# ============================================================

def discover_csv_files():
    if not AIS_DIR.exists():
        raise FileNotFoundError(
            f"AIS directory does not exist:\n{AIS_DIR}"
        )

    files = sorted(AIS_DIR.rglob("*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No CSV files found under:\n{AIS_DIR}"
        )

    return files


# ============================================================
# MAIN VERIFICATION
# ============================================================

def verify():

    csv_files = discover_csv_files()

    print("=" * 80)
    print("2019 SYNTHETIC AIS DATASET VERIFICATION")
    print("=" * 80)

    print(f"AIS directory : {AIS_DIR}")
    print(f"CSV files     : {len(csv_files)}")
    print()

    # --------------------------------------------------------
    # Global statistics
    # --------------------------------------------------------

    total_records = 0
    total_invalid_rows = 0

    missing_lat = 0
    missing_lon = 0
    missing_timestamp = 0
    invalid_timestamp = 0

    invalid_lat = 0
    invalid_lon = 0

    outside_region = 0

    invalid_speed = 0
    invalid_course = 0

    min_lat = float("inf")
    max_lat = float("-inf")
    min_lon = float("inf")
    max_lon = float("-inf")

    earliest_timestamp = None
    latest_timestamp = None

    vessels = set()

    # Duplicate detection
    duplicate_count = 0
    seen_records = set()

    # Monthly statistics
    monthly_records = defaultdict(int)
    monthly_vessels = defaultdict(set)

    # Vessel temporal statistics
    vessel_min_time = {}
    vessel_max_time = {}
    vessel_record_count = defaultdict(int)

    # Scenario statistics
    scenario_records = defaultdict(int)
    scenario_vessels = defaultdict(set)

    # --------------------------------------------------------
    # Process files
    # --------------------------------------------------------

    for file_index, csv_file in enumerate(csv_files, start=1):

        print(
            f"[{file_index}/{len(csv_files)}] "
            f"Processing {csv_file.name}"
        )

        with csv_file.open(
            "r",
            encoding="utf-8",
            errors="replace",
            newline=""
        ) as f:

            reader = csv.DictReader(f)

            if not reader.fieldnames:
                print("  WARNING: no header")
                continue

            headers = reader.fieldnames

            vessel_col = find_column(
                headers,
                [
                    "vessel_id",
                    "mmsi",
                    "ship_id",
                    "id"
                ]
            )

            timestamp_col = find_column(
                headers,
                [
                    "timestamp",
                    "time",
                    "datetime",
                    "date"
                ]
            )

            lat_col = find_column(
                headers,
                [
                    "latitude",
                    "lat"
                ]
            )

            lon_col = find_column(
                headers,
                [
                    "longitude",
                    "lon",
                    "lng"
                ]
            )

            speed_col = find_column(
                headers,
                [
                    "speed",
                    "speed_knots",
                    "sog"
                ]
            )

            course_col = find_column(
                headers,
                [
                    "course",
                    "cog",
                    "course_over_ground"
                ]
            )

            scenario_col = find_column(
                headers,
                [
                    "scenario_id",
                    "scenario"
                ]
            )

            required = {
                "vessel": vessel_col,
                "timestamp": timestamp_col,
                "latitude": lat_col,
                "longitude": lon_col,
            }

            missing_columns = [
                name
                for name, column in required.items()
                if column is None
            ]

            if missing_columns:
                raise RuntimeError(
                    f"{csv_file.name} is missing columns: "
                    f"{missing_columns}\n"
                    f"Available columns: {headers}"
                )

            for row_number, row in enumerate(reader, start=2):

                total_records += 1

                vessel_id = row.get(vessel_col)
                timestamp_raw = row.get(timestamp_col)
                lat_raw = row.get(lat_col)
                lon_raw = row.get(lon_col)

                # ------------------------------------------------
                # Vessel
                # ------------------------------------------------

                if not vessel_id:
                    total_invalid_rows += 1
                    continue

                vessels.add(vessel_id)

                vessel_record_count[vessel_id] += 1

                # ------------------------------------------------
                # Coordinates
                # ------------------------------------------------

                lat = parse_float(lat_raw)
                lon = parse_float(lon_raw)

                if lat is None:
                    missing_lat += 1
                elif not math.isfinite(lat):
                    invalid_lat += 1
                else:
                    min_lat = min(min_lat, lat)
                    max_lat = max(max_lat, lat)

                if lon is None:
                    missing_lon += 1
                elif not math.isfinite(lon):
                    invalid_lon += 1
                else:
                    min_lon = min(min_lon, lon)
                    max_lon = max(max_lon, lon)

                if (
                    lat is not None
                    and lon is not None
                    and math.isfinite(lat)
                    and math.isfinite(lon)
                ):
                    if (
                        lat < MIN_LAT
                        or lat > MAX_LAT
                        or lon < MIN_LON
                        or lon > MAX_LON
                    ):
                        outside_region += 1

                # ------------------------------------------------
                # Timestamp
                # ------------------------------------------------

                if not timestamp_raw:
                    missing_timestamp += 1
                    continue

                timestamp = parse_datetime(timestamp_raw)

                if timestamp is None:
                    invalid_timestamp += 1
                    continue

                # Global temporal bounds

                if earliest_timestamp is None:
                    earliest_timestamp = timestamp

                if latest_timestamp is None:
                    latest_timestamp = timestamp

                earliest_timestamp = min(
                    earliest_timestamp,
                    timestamp
                )

                latest_timestamp = max(
                    latest_timestamp,
                    timestamp
                )

                # Monthly statistics

                month = month_key(timestamp)

                monthly_records[month] += 1
                monthly_vessels[month].add(vessel_id)

                # Vessel temporal range

                if vessel_id not in vessel_min_time:
                    vessel_min_time[vessel_id] = timestamp
                    vessel_max_time[vessel_id] = timestamp
                else:
                    vessel_min_time[vessel_id] = min(
                        vessel_min_time[vessel_id],
                        timestamp
                    )

                    vessel_max_time[vessel_id] = max(
                        vessel_max_time[vessel_id],
                        timestamp
                    )

                # ------------------------------------------------
                # Speed
                # ------------------------------------------------

                if speed_col:

                    speed = parse_float(row.get(speed_col))

                    if speed is not None:
                        if not math.isfinite(speed) or speed < 0:
                            invalid_speed += 1

                # ------------------------------------------------
                # Course
                # ------------------------------------------------

                if course_col:

                    course = parse_float(row.get(course_col))

                    if course is not None:
                        if (
                            not math.isfinite(course)
                            or course < 0
                            or course > 360
                        ):
                            invalid_course += 1

                # ------------------------------------------------
                # Scenario
                # ------------------------------------------------

                if scenario_col:

                    scenario = row.get(scenario_col)

                    if scenario:

                        scenario_records[scenario] += 1
                        scenario_vessels[scenario].add(
                            vessel_id
                        )

                # ------------------------------------------------
                # Duplicate detection
                # ------------------------------------------------

                # Use a stable key based on the core AIS fields.
                duplicate_key = (
                    vessel_id,
                    timestamp_raw,
                    lat_raw,
                    lon_raw,
                )

                if duplicate_key in seen_records:
                    duplicate_count += 1
                else:
                    seen_records.add(duplicate_key)

        print(
            f"    Records processed: {total_records:,}"
        )

    # ============================================================
    # VALIDATION
    # ============================================================

    checks = {}

    checks["csv_files_found"] = len(csv_files) > 0

    checks["records_exist"] = total_records > 0

    checks["no_outside_region"] = outside_region == 0

    checks["no_missing_latitude"] = missing_lat == 0

    checks["no_missing_longitude"] = missing_lon == 0

    checks["no_invalid_latitude"] = invalid_lat == 0

    checks["no_invalid_longitude"] = invalid_lon == 0

    checks["no_missing_timestamp"] = missing_timestamp == 0

    checks["no_invalid_timestamp"] = invalid_timestamp == 0

    checks["no_duplicate_records"] = duplicate_count == 0

    checks["valid_speed_values"] = invalid_speed == 0

    checks["valid_course_values"] = invalid_course == 0

    checks["temporal_start"] = (
        earliest_timestamp is not None
        and earliest_timestamp <= EXPECTED_START
    )

    checks["temporal_end"] = (
        latest_timestamp is not None
        and latest_timestamp >= EXPECTED_END
    )

    checks["twelve_months_present"] = (
        len(monthly_records) == EXPECTED_MONTHS
    )

    overall_pass = all(checks.values())

    # ============================================================
    # PRINT RESULTS
    # ============================================================

    print()
    print("=" * 80)
    print("DATASET SUMMARY")
    print("=" * 80)

    print(f"Total records       : {total_records:,}")
    print(f"Unique vessels      : {len(vessels):,}")
    print(f"CSV files           : {len(csv_files)}")

    print()
    print("GEOGRAPHIC EXTENT")
    print("-" * 80)

    print(f"Minimum latitude    : {min_lat}")
    print(f"Maximum latitude    : {max_lat}")
    print(f"Minimum longitude   : {min_lon}")
    print(f"Maximum longitude   : {max_lon}")

    print()
    print("EXPECTED AIS REGION")
    print("-" * 80)

    print(f"Latitude            : {MIN_LAT} to {MAX_LAT}")
    print(f"Longitude           : {MIN_LON} to {MAX_LON}")

    print()
    print(f"Outside region      : {outside_region:,}")

    print()
    print("TEMPORAL COVERAGE")
    print("-" * 80)

    print(f"Earliest timestamp  : {earliest_timestamp}")
    print(f"Latest timestamp    : {latest_timestamp}")

    print()
    print("DATA QUALITY")
    print("-" * 80)

    print(f"Missing latitude    : {missing_lat:,}")
    print(f"Missing longitude   : {missing_lon:,}")
    print(f"Invalid latitude    : {invalid_lat:,}")
    print(f"Invalid longitude   : {invalid_lon:,}")
    print(f"Missing timestamp   : {missing_timestamp:,}")
    print(f"Invalid timestamp   : {invalid_timestamp:,}")
    print(f"Duplicate records   : {duplicate_count:,}")
    print(f"Invalid speed       : {invalid_speed:,}")
    print(f"Invalid course      : {invalid_course:,}")

    print()
    print("MONTHLY COVERAGE")
    print("-" * 80)

    for month in sorted(monthly_records):

        print(
            f"{month} | "
            f"records={monthly_records[month]:,} | "
            f"vessels={len(monthly_vessels[month]):,}"
        )

    print()
    print("VALIDATION CHECKS")
    print("-" * 80)

    for name, passed in checks.items():

        status = "PASS" if passed else "FAIL"

        print(
            f"{status:4} | {name}"
        )

    print()
    print("=" * 80)

    if overall_pass:
        print("OVERALL RESULT: PASS")
    else:
        print("OVERALL RESULT: FAIL")

    print("=" * 80)

    # ============================================================
    # BUILD REPORT
    # ============================================================

    report = {
        "dataset": {
            "directory": str(AIS_DIR),
            "csv_files": len(csv_files),
            "total_records": total_records,
            "unique_vessels": len(vessels),
        },

        "region": {
            "expected": {
                "min_lat": MIN_LAT,
                "max_lat": MAX_LAT,
                "min_lon": MIN_LON,
                "max_lon": MAX_LON,
            },
            "actual": {
                "min_lat": min_lat,
                "max_lat": max_lat,
                "min_lon": min_lon,
                "max_lon": max_lon,
            },
            "records_outside_region": outside_region,
        },

        "temporal": {
            "expected_start": EXPECTED_START.isoformat(),
            "expected_end": EXPECTED_END.isoformat(),
            "actual_start": (
                earliest_timestamp.isoformat()
                if earliest_timestamp
                else None
            ),
            "actual_end": (
                latest_timestamp.isoformat()
                if latest_timestamp
                else None
            ),
        },

        "quality": {
            "missing_latitude": missing_lat,
            "missing_longitude": missing_lon,
            "invalid_latitude": invalid_lat,
            "invalid_longitude": invalid_lon,
            "missing_timestamp": missing_timestamp,
            "invalid_timestamp": invalid_timestamp,
            "duplicate_records": duplicate_count,
            "invalid_speed": invalid_speed,
            "invalid_course": invalid_course,
        },

        "monthly": {
            month: {
                "records": monthly_records[month],
                "vessels": len(monthly_vessels[month]),
            }
            for month in sorted(monthly_records)
        },

        "scenarios": {
            scenario: {
                "records": scenario_records[scenario],
                "vessels": len(scenario_vessels[scenario]),
            }
            for scenario in sorted(scenario_records)
        },

        "checks": checks,

        "overall_pass": overall_pass,
    }

    # ============================================================
    # SAVE JSON
    # ============================================================

    JSON_REPORT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    # ============================================================
    # SAVE MARKDOWN
    # ============================================================

    md = []

    md.append("# 2019 Synthetic AIS Verification Report\n")

    md.append("## Dataset\n")

    md.append(f"- CSV files: {len(csv_files):,}")
    md.append(f"- Total records: {total_records:,}")
    md.append(f"- Unique vessels: {len(vessels):,}")

    md.append("\n## Geographic Coverage\n")

    md.append(
        f"- Expected latitude: `{MIN_LAT} → {MAX_LAT}`"
    )
    md.append(
        f"- Expected longitude: `{MIN_LON} → {MAX_LON}`"
    )
    md.append(f"- Actual minimum latitude: `{min_lat}`")
    md.append(f"- Actual maximum latitude: `{max_lat}`")
    md.append(f"- Actual minimum longitude: `{min_lon}`")
    md.append(f"- Actual maximum longitude: `{max_lon}`")
    md.append(
        f"- Records outside region: **{outside_region:,}**"
    )

    md.append("\n## Temporal Coverage\n")

    md.append(
        f"- Expected start: `{EXPECTED_START.isoformat()}`"
    )
    md.append(
        f"- Expected end: `{EXPECTED_END.isoformat()}`"
    )
    md.append(
        f"- Actual start: `{earliest_timestamp}`"
    )
    md.append(
        f"- Actual end: `{latest_timestamp}`"
    )

    md.append("\n## Data Quality\n")

    md.append(f"- Missing latitude: {missing_lat:,}")
    md.append(f"- Missing longitude: {missing_lon:,}")
    md.append(f"- Invalid latitude: {invalid_lat:,}")
    md.append(f"- Invalid longitude: {invalid_lon:,}")
    md.append(f"- Missing timestamps: {missing_timestamp:,}")
    md.append(f"- Invalid timestamps: {invalid_timestamp:,}")
    md.append(f"- Duplicate records: {duplicate_count:,}")
    md.append(f"- Invalid speed: {invalid_speed:,}")
    md.append(f"- Invalid course: {invalid_course:,}")

    md.append("\n## Monthly Coverage\n")

    md.append("| Month | Records | Vessels |")
    md.append("|---|---:|---:|")

    for month in sorted(monthly_records):

        md.append(
            f"| {month} | "
            f"{monthly_records[month]:,} | "
            f"{len(monthly_vessels[month]):,} |"
        )

    md.append("\n## Validation Checks\n")

    md.append("| Check | Result |")
    md.append("|---|---|")

    for name, passed in checks.items():

        md.append(
            f"| {name} | "
            f"{'PASS' if passed else 'FAIL'} |"
        )

    md.append("\n## Overall Result\n")

    md.append(
        f"**{'PASS' if overall_pass else 'FAIL'}**"
    )

    MD_REPORT.write_text(
        "\n".join(md),
        encoding="utf-8"
    )

    print()
    print(f"JSON report : {JSON_REPORT}")
    print(f"MD report   : {MD_REPORT}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    try:
        sys.exit(verify())
    except KeyboardInterrupt:
        print("\nVerification cancelled.")
        sys.exit(130)
    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        sys.exit(1)