from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# PROJECT PATH
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# STANDARD LIBRARY
# ---------------------------------------------------------------------------

import asyncio
import csv
import json
import time

from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# THIRD-PARTY
# ---------------------------------------------------------------------------

from sqlalchemy import text


# ---------------------------------------------------------------------------
# APPLICATION IMPORTS
# ---------------------------------------------------------------------------

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

COAST_DIR = PROJECT_ROOT / "json_output" / "coast"
WATER_DIR = PROJECT_ROOT / "json_output" / "water"

OUTPUT_DIR = PROJECT_ROOT / "json_output" / "validation"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CSV_OUTPUT = OUTPUT_DIR / "detection_attribution_results.csv"
JSON_OUTPUT = OUTPUT_DIR / "detection_attribution_summary.json"


# ---------------------------------------------------------------------------
# EXPECTED COUNTS
# ---------------------------------------------------------------------------

EXPECTED_DETECTIONS = 2165
EXPECTED_COAST_DETECTIONS = 544
EXPECTED_WATER_DETECTIONS = 1621


# ---------------------------------------------------------------------------
# LOAD DETECTIONS
# ---------------------------------------------------------------------------

def load_detections() -> list[dict]:
    """
    Load all detections from coast and water JSON files.

    A single JSON file can contain multiple detections, so the count
    is based on detection objects rather than number of files.
    """

    detections = []

    sources = [
        ("coast", COAST_DIR, "oc-*.json"),
        ("water", WATER_DIR, "ow-*.json"),
    ]

    for source_type, directory, pattern in sources:

        files = sorted(directory.glob(pattern))

        print()
        print(source_type.upper())
        print(f"Directory : {directory}")
        print(f"Files     : {len(files)}")

        for file_path in files:

            try:

                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                ) as f:
                    data = json.load(f)

                file_detections = data.get(
                    "detections",
                    [],
                )

                if not isinstance(file_detections, list):
                    print(
                        f"WARNING: {file_path.name} "
                        f"has invalid 'detections' field"
                    )
                    continue

                for detection in file_detections:

                    if not isinstance(detection, dict):
                        print(
                            f"WARNING: invalid detection in "
                            f"{file_path.name}"
                        )
                        continue

                    detection["_source_type"] = source_type
                    detection["_source_file"] = file_path.name

                    detections.append(detection)

            except Exception as exc:

                print(
                    f"ERROR reading {file_path.name}: {exc}",
                    file=sys.stderr,
                )

    return detections


# ---------------------------------------------------------------------------
# DATETIME
# ---------------------------------------------------------------------------

def parse_datetime(value: str) -> datetime:
    """
    Convert ISO timestamp into timezone-aware UTC datetime.
    """

    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# RELEASE TIME
# ---------------------------------------------------------------------------

def calculate_release_time(
    detection: dict,
) -> datetime:
    """
    Estimate release time from:

        detected_at - estimated_age_hours
    """

    detected_at = parse_datetime(
        detection["detected_at"]
    )

    age_hours = float(
        detection["estimated_age_hours"]
    )

    return detected_at - timedelta(
        hours=age_hours
    )


# ---------------------------------------------------------------------------
# DATABASE CHECK
# ---------------------------------------------------------------------------

async def validate_database():
    """
    Verify database connectivity and report AIS size.
    """

    async with AsyncSessionLocal() as db:

        result = await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ais_positions
                """
            )
        )

        count = result.scalar_one()

    print()
    print("DATABASE")
    print(f"AIS records : {count:,}")


# ---------------------------------------------------------------------------
# CREATE ATTRIBUTION ENGINE
# ---------------------------------------------------------------------------

def create_engine():
    """
    Create the same WeatherService configuration used by the API.

    Uses yearly ERA5/CMEMS environmental datasets.
    """

    weather_service = WeatherService(
        weather_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "weather"
            / "raw"
            / "yearly"
        ),
        ocean_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "ocean"
            / "raw"
            / "yearly"
        ),
    )

    engine = AttributionEngine(
        weather_service=weather_service
    )

    return engine, weather_service


# ---------------------------------------------------------------------------
# PROCESS ONE DETECTION
# ---------------------------------------------------------------------------

async def process_detection(
    engine: AttributionEngine,
    db,
    detection: dict,
    index: int,
    total: int,
) -> dict:

    spill_id = detection["spill_id"]

    detected_at = parse_datetime(
        detection["detected_at"]
    )

    latitude = float(
        detection["centroid"]["lat"]
    )

    longitude = float(
        detection["centroid"]["lon"]
    )

    age_hours = float(
        detection["estimated_age_hours"]
    )

    release_time = (
        detected_at
        - timedelta(hours=age_hours)
    )

    started = time.perf_counter()

    # -----------------------------------------------------------------------
    # FULL SYNTHETIC AIS POPULATION
    #
    # synthetic_only=True
    # scenario_id=None
    #
    # This intentionally does NOT restrict the search to a scenario.
    # -----------------------------------------------------------------------

    result = await engine.attribute(
        db=db,

        observation_latitude=latitude,
        observation_longitude=longitude,

        observation_time=detected_at,

        drift_duration_hours=age_hours,

        ensemble_size=100,
        initial_radius_m=500.0,
        timestep_minutes=15,

        candidate_radius_margin_km=5.0,
        candidate_time_window_hours=2.0,

        synthetic_only=True,
        scenario_id=None,
    )

    elapsed = (
        time.perf_counter()
        - started
    )

    # -----------------------------------------------------------------------
    # SOURCE ESTIMATE
    # -----------------------------------------------------------------------

    source_estimate = result.get(
        "source_estimate",
        {},
    )

    # -----------------------------------------------------------------------
    # CANDIDATES
    # -----------------------------------------------------------------------

    candidates = result.get(
        "candidates",
        [],
    )

    candidate_count = result.get(
        "candidate_count",
        len(candidates),
    )

    ranked_top_vessel = None
    ranked_top_score = None

    if candidates:

        ranked_top_vessel = candidates[0].get(
            "vessel_id"
        )

        ranked_top_score = candidates[0].get(
            "total_score"
        )

    # -----------------------------------------------------------------------
    # RESULT ROW
    # -----------------------------------------------------------------------

    row = {
        "spill_id": spill_id,

        "source_type": detection.get(
            "_source_type"
        ),

        "source_file": detection.get(
            "_source_file"
        ),

        "detected_at": detected_at.isoformat(),

        "estimated_age_hours": age_hours,

        "estimated_release_time": (
            release_time.isoformat()
        ),

        "observation_latitude": latitude,

        "observation_longitude": longitude,

        "confidence_score": detection.get(
            "confidence_score"
        ),

        "area_km2": detection.get(
            "area_km2"
        ),

        "estimated_source_latitude": (
            source_estimate.get("latitude")
        ),

        "estimated_source_longitude": (
            source_estimate.get("longitude")
        ),

        "estimated_source_radius_km": (
            source_estimate.get("radius_km")
        ),

        "candidate_count": candidate_count,

        "ranked_top_vessel": ranked_top_vessel,

        "top_prediction": result.get(
            "top_prediction"
        ),

        "ranked_top_score": ranked_top_score,

        "runtime_seconds": round(
            elapsed,
            3,
        ),

        "status": "SUCCESS",

        "error": "",
    }

    # -----------------------------------------------------------------------
    # PROGRESS
    # -----------------------------------------------------------------------

    print(
        f"[{index:4}/{total}] "
        f"{spill_id:<18} "
        f"{detection.get('_source_type', ''):<6} "
        f"candidates={str(candidate_count):<4} "
        f"top={str(ranked_top_vessel):<24} "
        f"time={elapsed:.2f}s"
    )

    return row


# ---------------------------------------------------------------------------
# FAILED RESULT
# ---------------------------------------------------------------------------

def create_failed_row(
    detection: dict,
    exc: Exception,
) -> dict:

    centroid = detection.get(
        "centroid",
        {},
    )

    return {
        "spill_id": detection.get(
            "spill_id"
        ),

        "source_type": detection.get(
            "_source_type"
        ),

        "source_file": detection.get(
            "_source_file"
        ),

        "detected_at": detection.get(
            "detected_at"
        ),

        "estimated_age_hours": detection.get(
            "estimated_age_hours"
        ),

        "estimated_release_time": "",

        "observation_latitude": centroid.get(
            "lat"
        ),

        "observation_longitude": centroid.get(
            "lon"
        ),

        "confidence_score": detection.get(
            "confidence_score"
        ),

        "area_km2": detection.get(
            "area_km2"
        ),

        "estimated_source_latitude": "",

        "estimated_source_longitude": "",

        "estimated_source_radius_km": "",

        "candidate_count": "",

        "ranked_top_vessel": "",

        "top_prediction": "",

        "ranked_top_score": "",

        "runtime_seconds": "",

        "status": "FAILED",

        "error": repr(exc),
    }


# ---------------------------------------------------------------------------
# SAVE CSV
# ---------------------------------------------------------------------------

def save_csv(
    results: list[dict],
):
    """

    Save individual detection results.
    """

    fieldnames = [
        "spill_id",
        "source_type",
        "source_file",
        "detected_at",
        "estimated_age_hours",
        "estimated_release_time",
        "observation_latitude",
        "observation_longitude",
        "confidence_score",
        "area_km2",
        "estimated_source_latitude",
        "estimated_source_longitude",
        "estimated_source_radius_km",
        "candidate_count",
        "ranked_top_vessel",
        "top_prediction",
        "ranked_top_score",
        "runtime_seconds",
        "status",
        "error",
    ]

    with open(
        CSV_OUTPUT,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(results)


# ---------------------------------------------------------------------------
# SAVE SUMMARY
# ---------------------------------------------------------------------------

def save_summary(
    detections: list[dict],
    results: list[dict],
):

    coast_detections = [
        d
        for d in detections
        if d.get("_source_type") == "coast"
    ]

    water_detections = [
        d
        for d in detections
        if d.get("_source_type") == "water"
    ]

    successful_results = [
        r
        for r in results
        if r["status"] == "SUCCESS"
    ]

    failed_results = [
        r
        for r in results
        if r["status"] == "FAILED"
    ]

    candidate_counts = []

    for result in successful_results:

        value = result.get(
            "candidate_count"
        )

        if value != "":
            candidate_counts.append(
                int(value)
            )

    runtimes = []

    for result in successful_results:

        value = result.get(
            "runtime_seconds"
        )

        if value != "":
            runtimes.append(
                float(value)
            )

    summary = {
        "expected_detections": (
            EXPECTED_DETECTIONS
        ),

        "actual_detections": len(
            detections
        ),

        "count_validation": {
            "passed": (
                len(detections)
                == EXPECTED_DETECTIONS
            ),

            "expected_coast": (
                EXPECTED_COAST_DETECTIONS
            ),

            "actual_coast": len(
                coast_detections
            ),

            "expected_water": (
                EXPECTED_WATER_DETECTIONS
            ),

            "actual_water": len(
                water_detections
            ),
        },

        "attribution": {
            "successful": len(
                successful_results
            ),

            "failed": len(
                failed_results
            ),
        },

        "candidate_statistics": {
            "min": (
                min(candidate_counts)
                if candidate_counts
                else None
            ),

            "max": (
                max(candidate_counts)
                if candidate_counts
                else None
            ),

            "average": (
                sum(candidate_counts)
                / len(candidate_counts)
                if candidate_counts
                else None
            ),
        },

        "runtime_statistics": {
            "total_seconds": (
                sum(runtimes)
                if runtimes
                else 0
            ),

            "total_minutes": (
                sum(runtimes) / 60
                if runtimes
                else 0
            ),

            "average_seconds": (
                sum(runtimes)
                / len(runtimes)
                if runtimes
                else None
            ),

            "min_seconds": (
                min(runtimes)
                if runtimes
                else None
            ),

            "max_seconds": (
                max(runtimes)
                if runtimes
                else None
            ),
        },

        "outputs": {
            "csv": str(
                CSV_OUTPUT
            ),

            "summary": str(
                JSON_OUTPUT
            ),
        },
    }

    with open(
        JSON_OUTPUT,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            summary,
            f,
            indent=2,
        )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

async def main():

    print("=" * 90)
    print(
        "2165 DETECTION ATTRIBUTION VALIDATION"
    )
    print("=" * 90)

    # -----------------------------------------------------------------------
    # LOAD DETECTIONS
    # -----------------------------------------------------------------------

    detections = load_detections()

    coast_count = sum(
        1
        for d in detections
        if d.get("_source_type") == "coast"
    )

    water_count = sum(
        1
        for d in detections
        if d.get("_source_type") == "water"
    )

    print()
    print("=" * 90)
    print("DETECTION COUNTS")
    print("=" * 90)

    print(
        f"Coast detections : {coast_count:,}"
    )

    print(
        f"Water detections : {water_count:,}"
    )

    print(
        f"TOTAL detections : {len(detections):,}"
    )

    # -----------------------------------------------------------------------
    # COUNT VALIDATION
    # -----------------------------------------------------------------------

    if (
        coast_count == EXPECTED_COAST_DETECTIONS
        and water_count == EXPECTED_WATER_DETECTIONS
        and len(detections) == EXPECTED_DETECTIONS
    ):

        print()
        print(
            "Detection count validation : PASS"
        )

    else:

        print()
        print(
            "Detection count validation : FAIL"
        )

        print(
            f"Expected coast : "
            f"{EXPECTED_COAST_DETECTIONS}"
        )

        print(
            f"Actual coast   : "
            f"{coast_count}"
        )

        print(
            f"Expected water : "
            f"{EXPECTED_WATER_DETECTIONS}"
        )

        print(
            f"Actual water   : "
            f"{water_count}"
        )

        print(
            f"Expected total : "
            f"{EXPECTED_DETECTIONS}"
        )

        print(
            f"Actual total   : "
            f"{len(detections)}"
        )

        print(
            "\nStopping before attribution."
        )

        return

    # -----------------------------------------------------------------------
    # DATABASE
    # -----------------------------------------------------------------------

    await validate_database()

    # -----------------------------------------------------------------------
    # ATTRIBUTION ENGINE
    # -----------------------------------------------------------------------

    engine, weather_service = create_engine()

    results = []

    successful = 0
    failed = 0

    total = len(detections)

    print()
    print("=" * 90)
    print("RUNNING ATTRIBUTION")
    print("=" * 90)

    overall_start = time.perf_counter()

    try:

        async with AsyncSessionLocal() as db:

            for index, detection in enumerate(
                detections,
                start=1,
            ):

                try:

                    row = await process_detection(
                        engine=engine,
                        db=db,
                        detection=detection,
                        index=index,
                        total=total,
                    )

                    results.append(row)

                    successful += 1

                except Exception as exc:

                    failed += 1

                    row = create_failed_row(
                        detection=detection,
                        exc=exc,
                    )

                    results.append(row)

                    print(
                        f"[{index:4}/{total}] "
                        f"{detection.get('spill_id')} "
                        f"FAILED: {exc}",
                        file=sys.stderr,
                    )

    finally:

        weather_service.close()

    overall_elapsed = (
        time.perf_counter()
        - overall_start
    )

    # -----------------------------------------------------------------------
    # SAVE RESULTS
    # -----------------------------------------------------------------------

    save_csv(results)

    save_summary(
        detections=detections,
        results=results,
    )

    # -----------------------------------------------------------------------
    # FINAL SUMMARY
    # -----------------------------------------------------------------------

    successful_results = [
        r
        for r in results
        if r["status"] == "SUCCESS"
    ]

    candidate_counts = [
        int(r["candidate_count"])
        for r in successful_results
        if r["candidate_count"] != ""
    ]

    runtimes = [
        float(r["runtime_seconds"])
        for r in successful_results
        if r["runtime_seconds"] != ""
    ]

    print()
    print("=" * 90)
    print("FINAL SUMMARY")
    print("=" * 90)

    print(
        f"Expected detections : "
        f"{EXPECTED_DETECTIONS:,}"
    )

    print(
        f"Actual detections   : "
        f"{len(detections):,}"
    )

    print(
        f"Coast               : "
        f"{coast_count:,}"
    )

    print(
        f"Water               : "
        f"{water_count:,}"
    )

    print(
        f"Successful          : "
        f"{successful:,}"
    )

    print(
        f"Failed              : "
        f"{failed:,}"
    )

    print(
        f"Wall-clock runtime  : "
        f"{overall_elapsed / 60:.2f} minutes"
    )

    if runtimes:

        print(
            f"Average attribution : "
            f"{sum(runtimes) / len(runtimes):.2f}s"
        )

        print(
            f"Min attribution     : "
            f"{min(runtimes):.2f}s"
        )

        print(
            f"Max attribution     : "
            f"{max(runtimes):.2f}s"
        )

    if candidate_counts:

        print(
            f"Average candidates  : "
            f"{sum(candidate_counts) / len(candidate_counts):.2f}"
        )

        print(
            f"Min candidates      : "
            f"{min(candidate_counts)}"
        )

        print(
            f"Max candidates      : "
            f"{max(candidate_counts)}"
        )

    print()
    print("OUTPUT FILES")
    print(
        f"CSV     : {CSV_OUTPUT}"
    )

    print(
        f"Summary : {JSON_OUTPUT}"
    )

    print()
    print("DONE")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())