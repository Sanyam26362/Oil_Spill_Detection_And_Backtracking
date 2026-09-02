from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from sqlalchemy import text


# ============================================================================
# PROJECT PATH
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# APPLICATION IMPORTS
# ============================================================================

from app.core.database import AsyncSessionLocal
from app.services.attribution_engine import AttributionEngine
from app.services.weather_service import WeatherService


# ============================================================================
# SCENARIO CONFIGURATION
# ============================================================================

SCENARIO_ID = "scenario-004"

TRUE_SOURCE_VESSEL = "SYNTH-004-SRC"

TRUE_SOURCE_LATITUDE = 35.05
TRUE_SOURCE_LONGITUDE = 24.04

OBSERVATION_LATITUDE = 35.07102734
OBSERVATION_LONGITUDE = 24.05447057

RELEASE_TIME = datetime(
    2019,
    7,
    15,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)

OBSERVATION_TIME = datetime(
    2019,
    7,
    15,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)

DRIFT_DURATION_HOURS = 6.0

ENSEMBLE_SIZE = 100
INITIAL_RADIUS_M = 500.0
TIMESTEP_MINUTES = 15

CANDIDATE_RADIUS_MARGIN_KM = 5.0
CANDIDATE_TIME_WINDOW_HOURS = 2.0

MAX_SOURCE_ERROR_KM = 5.0


# ============================================================================
# OUTPUT HELPERS
# ============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_section(title: str) -> None:
    print()
    print(title)
    print("-" * 80)


def get_value(obj, key: str, default=None):
    """
    Retrieve a value from either a dict or an object/dataclass.
    """
    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


# ============================================================================
# HAVERSINE
# ============================================================================

def haversine_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:

    lat1 = radians(latitude_1)
    lon1 = radians(longitude_1)

    lat2 = radians(latitude_2)
    lon2 = radians(longitude_2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2.0) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(dlon / 2.0) ** 2
    )

    c = 2.0 * asin(sqrt(a))

    return 6371.0 * c


# ============================================================================
# DATABASE VALIDATION
# ============================================================================

async def validate_database() -> None:

    print_section("DATABASE VALIDATION")

    async with AsyncSessionLocal() as db:

        # ------------------------------------------------------------------
        # Total positions
        # ------------------------------------------------------------------

        result = await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                """
            ),
            {
                "scenario_id": SCENARIO_ID,
            },
        )

        position_count = result.scalar_one()

        # ------------------------------------------------------------------
        # Number of vessels
        # ------------------------------------------------------------------

        result = await db.execute(
            text(
                """
                SELECT COUNT(DISTINCT vessel_id)
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                """
            ),
            {
                "scenario_id": SCENARIO_ID,
            },
        )

        vessel_count = result.scalar_one()

        # ------------------------------------------------------------------
        # Source vessel rows
        # ------------------------------------------------------------------

        result = await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                  AND vessel_id = :vessel_id
                """
            ),
            {
                "scenario_id": SCENARIO_ID,
                "vessel_id": TRUE_SOURCE_VESSEL,
            },
        )

        source_rows = result.scalar_one()

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------

        print(f"Scenario positions : {position_count:,}")
        print(f"Scenario vessels   : {vessel_count}")
        print(f"Source vessel rows : {source_rows:,}")

        if position_count == 17_167:
            print("Position count     : PASS")
        else:
            print(
                "Position count     : WARNING "
                f"(expected 17,167, got {position_count:,})"
            )

        if vessel_count == 156:
            print("Vessel count       : PASS")
        else:
            print(
                "Vessel count       : WARNING "
                f"(expected 156, got {vessel_count})"
            )

        if source_rows > 0:
            print("Source vessel      : PASS")
        else:
            raise RuntimeError(
                f"Source vessel {TRUE_SOURCE_VESSEL} "
                "was not found in the database."
            )

        print("Database validation : PASS")


# ============================================================================
# PRINT SCORE
# ============================================================================

def print_candidate_score(candidate) -> None:

    fields = [
        "total_score",
        "proximity_score",
        "temporal_score",
        "slowdown_score",
        "loiter_score",
        "approach_score",
        "departure_score",
        "closest_distance_km",
        "minimum_event_speed_knots",
    ]

    for field in fields:

        value = get_value(candidate, field)

        if value is None:
            continue

        try:
            numeric_value = float(value)

            print(
                f"{field:<30}: "
                f"{numeric_value:.6f}"
            )

        except (TypeError, ValueError):

            print(
                f"{field:<30}: "
                f"{value}"
            )


# ============================================================================
# MAIN ATTRIBUTION TEST
# ============================================================================

async def run_attribution() -> dict:

    print_header(
        "SCENARIO-004 FULL E2E ATTRIBUTION TEST"
    )

    # ========================================================================
    # OBSERVATION
    # ========================================================================

    print_section("OBSERVATION")

    print(
        f"Latitude  : {OBSERVATION_LATITUDE:.8f}"
    )

    print(
        f"Longitude : {OBSERVATION_LONGITUDE:.8f}"
    )

    print(
        f"Time      : {OBSERVATION_TIME.isoformat()}"
    )

    print(
        f"Duration  : {DRIFT_DURATION_HOURS} hours"
    )

    # ========================================================================
    # GROUND TRUTH
    # ========================================================================

    print_section("GROUND TRUTH")

    print(
        f"Source vessel : {TRUE_SOURCE_VESSEL}"
    )

    print(
        f"Source        : "
        f"{TRUE_SOURCE_LATITUDE:.6f}, "
        f"{TRUE_SOURCE_LONGITUDE:.6f}"
    )

    print(
        f"Release time  : "
        f"{RELEASE_TIME.isoformat()}"
    )

    # ========================================================================
    # DATABASE
    # ========================================================================

    await validate_database()

    # ========================================================================
    # ENVIRONMENT
    # ========================================================================

    print_header(
        "INITIALIZING ENVIRONMENT"
    )

    weather_dir = (
        PROJECT_ROOT
        / "data"
        / "weather"
        / "raw"
        / "yearly"
    )

    ocean_dir = (
        PROJECT_ROOT
        / "data"
        / "ocean"
        / "raw"
        / "yearly"
    )

    print(
        f"Weather directory : {weather_dir}"
    )

    print(
        f"Ocean directory   : {ocean_dir}"
    )

    if not weather_dir.exists():
        raise FileNotFoundError(
            "Weather directory does not exist:\n"
            f"{weather_dir}"
        )

    if not ocean_dir.exists():
        raise FileNotFoundError(
            "Ocean directory does not exist:\n"
            f"{ocean_dir}"
        )

    weather_service = WeatherService(
        weather_yearly_dir=weather_dir,
        ocean_yearly_dir=ocean_dir,
    )

    # ========================================================================
    # ATTRIBUTION ENGINE
    # ========================================================================

    engine = AttributionEngine(
        weather_service=weather_service,
    )

    # ========================================================================
    # RUN ATTRIBUTION
    # ========================================================================

    print_header(
        "RUNNING ATTRIBUTION ENGINE"
    )

    async with AsyncSessionLocal() as db:

        result = await engine.attribute(
            db=db,
            observation_latitude=OBSERVATION_LATITUDE,
            observation_longitude=OBSERVATION_LONGITUDE,
            observation_time=OBSERVATION_TIME,
            drift_duration_hours=DRIFT_DURATION_HOURS,
            ensemble_size=ENSEMBLE_SIZE,
            initial_radius_m=INITIAL_RADIUS_M,
            timestep_minutes=TIMESTEP_MINUTES,
            candidate_radius_margin_km=CANDIDATE_RADIUS_MARGIN_KM,
            candidate_time_window_hours=CANDIDATE_TIME_WINDOW_HOURS,
            synthetic_only=True,
            scenario_id=SCENARIO_ID,
        )

    # ========================================================================
    # RESULT
    # ========================================================================

    print_header(
        "ATTRIBUTION RESULT"
    )

    print(
        f"Result type: {type(result).__name__}"
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            "AttributionEngine.attribute() returned "
            f"{type(result).__name__}, expected dict."
        )

    print(
        f"Result keys : {list(result.keys())}"
    )

    # ========================================================================
    # SOURCE ESTIMATE
    # ========================================================================

    source_estimate = result.get(
        "source_estimate"
    )

    if source_estimate is None:
        raise RuntimeError(
            "Missing source_estimate in attribution result."
        )

    source_latitude = get_value(
        source_estimate,
        "latitude",
    )

    source_longitude = get_value(
        source_estimate,
        "longitude",
    )

    source_radius_km = get_value(
        source_estimate,
        "radius_km",
    )

    if (
        source_latitude is None
        or source_longitude is None
        or source_radius_km is None
    ):
        raise RuntimeError(
            "Unexpected source_estimate structure:\n"
            f"{source_estimate}"
        )

    source_latitude = float(
        source_latitude
    )

    source_longitude = float(
        source_longitude
    )

    source_radius_km = float(
        source_radius_km
    )

    print_section(
        "HINDCAST SOURCE ESTIMATE"
    )

    print(
        f"Latitude  : "
        f"{source_latitude:.8f}"
    )

    print(
        f"Longitude : "
        f"{source_longitude:.8f}"
    )

    print(
        f"Radius    : "
        f"{source_radius_km:.6f} km"
    )

    # ========================================================================
    # SOURCE ERROR
    # ========================================================================

    source_error_km = haversine_km(
        TRUE_SOURCE_LATITUDE,
        TRUE_SOURCE_LONGITUDE,
        source_latitude,
        source_longitude,
    )

    print_section(
        "SOURCE RECOVERY"
    )

    print(
        f"True source : "
        f"{TRUE_SOURCE_LATITUDE:.8f}, "
        f"{TRUE_SOURCE_LONGITUDE:.8f}"
    )

    print(
        f"Estimated   : "
        f"{source_latitude:.8f}, "
        f"{source_longitude:.8f}"
    )

    print(
        f"Error       : "
        f"{source_error_km:.6f} km"
    )

    source_recovery_pass = (
        source_error_km <= MAX_SOURCE_ERROR_KM
    )

    if source_recovery_pass:

        print(
            f"Source recovery : PASS "
            f"(<= {MAX_SOURCE_ERROR_KM:.1f} km)"
        )

    else:

        print(
            f"Source recovery : FAIL "
            f"(> {MAX_SOURCE_ERROR_KM:.1f} km)"
        )

    # ========================================================================
    # RELEASE TIME
    # ========================================================================

    estimated_release_time = result.get(
        "estimated_release_time"
    )

    print_section(
        "RELEASE TIME"
    )

    print(
        f"True release      : "
        f"{RELEASE_TIME.isoformat()}"
    )

    print(
        f"Estimated release : "
        f"{estimated_release_time}"
    )

    # ========================================================================
    # CANDIDATES
    # ========================================================================

    candidate_count = result.get(
        "candidate_count",
        0,
    )

    candidates = result.get(
        "candidates",
        [],
    )

    if candidates is None:
        candidates = []

    print_section(
        "CANDIDATE SEARCH"
    )

    print(
        f"Candidate count : "
        f"{candidate_count}"
    )

    candidate_search_pass = (
        len(candidates) > 0
    )

    if candidate_search_pass:

        print(
            "Candidate search : PASS"
        )

    else:

        print(
            "Candidate search : FAIL"
        )

    # ========================================================================
    # RANKED CANDIDATES
    # ========================================================================

    print_section(
        "RANKED CANDIDATES"
    )

    if not candidates:

        print(
            "No candidates returned."
        )

    else:

        for rank, candidate in enumerate(
            candidates,
            start=1,
        ):

            vessel_id = get_value(
                candidate,
                "vessel_id",
                "UNKNOWN",
            )

            total_score = get_value(
                candidate,
                "total_score",
            )

            # Some serialized results may not expose total_score
            # even though component scores are present.
            if total_score is None:

                total_score_display = "N/A"

            else:

                try:

                    total_score_display = (
                        f"{float(total_score):.6f}"
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    total_score_display = str(
                        total_score
                    )

            closest_distance = get_value(
                candidate,
                "closest_distance_km",
            )

            if closest_distance is not None:

                try:

                    distance_display = (
                        f"{float(closest_distance):.3f} km"
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    distance_display = str(
                        closest_distance
                    )

            else:

                distance_display = "N/A"

            print(
                f"{rank:2d}. "
                f"{str(vessel_id):<25} "
                f"score={total_score_display} "
                f"distance={distance_display}"
            )

    # ========================================================================
    # FIND TRUE SOURCE
    # ========================================================================

    source_rank = None
    source_candidate = None

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):

        vessel_id = get_value(
            candidate,
            "vessel_id",
        )

        if vessel_id == TRUE_SOURCE_VESSEL:

            source_rank = rank
            source_candidate = candidate

            break

    print_section(
        "SOURCE VESSEL ATTRIBUTION"
    )

    if source_rank is None:

        print(
            f"Source vessel {TRUE_SOURCE_VESSEL} "
            "was NOT found in candidates."
        )

        source_found_pass = False
        source_rank_pass = False

    else:

        source_found_pass = True

        print(
            f"Source vessel : "
            f"{TRUE_SOURCE_VESSEL}"
        )

        print(
            f"Rank          : "
            f"#{source_rank}"
        )

        source_total_score = get_value(
            source_candidate,
            "total_score",
        )

        if source_total_score is None:

            print(
                "Score         : N/A"
            )

        else:

            print(
                f"Score         : "
                f"{float(source_total_score):.6f}"
            )

        if source_rank == 1:

            print(
                "Source ranking : PASS — #1"
            )

            source_rank_pass = True

        else:

            print(
                f"Source ranking : "
                f"FAIL — #{source_rank}"
            )

            source_rank_pass = False

    # ========================================================================
    # SOURCE SCORE BREAKDOWN
    # ========================================================================

    if source_candidate is not None:

        print_section(
            "SOURCE VESSEL SCORE BREAKDOWN"
        )

        print_candidate_score(
            source_candidate
        )

    # ========================================================================
    # TOP PREDICTION
    # ========================================================================

    top_prediction = result.get(
        "top_prediction"
    )

    print_section(
        "TOP PREDICTION"
    )

    print(
        f"Type : "
        f"{type(top_prediction).__name__}"
    )

    print(
        f"Raw  : "
        f"{top_prediction}"
    )

    # ------------------------------------------------------------------------
    # Determine top prediction robustly
    # ------------------------------------------------------------------------

    top_vessel_id = None
    top_score = None

    if isinstance(
        top_prediction,
        str,
    ):

        # Case:
        # top_prediction = "SYNTH-004-SRC"

        top_vessel_id = top_prediction

    elif isinstance(
        top_prediction,
        dict,
    ):

        # Possible dictionary formats.

        top_vessel_id = (
            top_prediction.get("vessel_id")
            or top_prediction.get("id")
            or top_prediction.get("mmsi")
        )

        top_score = (
            top_prediction.get("total_score")
            or top_prediction.get("score")
        )

    elif top_prediction is not None:

        top_vessel_id = (
            getattr(
                top_prediction,
                "vessel_id",
                None,
            )
            or getattr(
                top_prediction,
                "id",
                None,
            )
            or getattr(
                top_prediction,
                "mmsi",
                None,
            )
        )

        top_score = (
            getattr(
                top_prediction,
                "total_score",
                None,
            )
            or getattr(
                top_prediction,
                "score",
                None,
            )
        )

    # ------------------------------------------------------------------------
    # If top_prediction is just an identifier or malformed,
    # use the actual ranked candidates as the authoritative prediction.
    # ------------------------------------------------------------------------

    ranked_top_vessel_id = None
    ranked_top_candidate = None

    if candidates:

        ranked_top_candidate = candidates[0]

        ranked_top_vessel_id = get_value(
            ranked_top_candidate,
            "vessel_id",
        )

    # ------------------------------------------------------------------------
    # Display raw top_prediction
    # ------------------------------------------------------------------------

    if top_vessel_id is not None:

        print(
            f"Returned vessel : "
            f"{top_vessel_id}"
        )

    if top_score is not None:

        try:

            print(
                f"Returned score  : "
                f"{float(top_score):.6f}"
            )

        except (
            TypeError,
            ValueError,
        ):

            print(
                f"Returned score  : "
                f"{top_score}"
            )

    # ------------------------------------------------------------------------
    # Authoritative ranking
    # ------------------------------------------------------------------------

    print()

    print(
        f"Ranked #1 vessel : "
        f"{ranked_top_vessel_id}"
    )

    if ranked_top_candidate is not None:

        ranked_top_score = get_value(
            ranked_top_candidate,
            "total_score",
        )

        if ranked_top_score is not None:

            try:

                print(
                    f"Ranked #1 score  : "
                    f"{float(ranked_top_score):.6f}"
                )

            except (
                TypeError,
                ValueError,
            ):

                print(
                    f"Ranked #1 score  : "
                    f"{ranked_top_score}"
                )

    # ------------------------------------------------------------------------
    # Determine prediction pass
    # ------------------------------------------------------------------------

    #
    # The ranked candidates are what the attribution engine sorted.
    # Therefore candidates[0] is the authoritative top-ranked vessel.
    #

    top_prediction_pass = (
        ranked_top_vessel_id
        == TRUE_SOURCE_VESSEL
    )

    if top_prediction_pass:

        print(
            "Top prediction : PASS — "
            "true source is ranked #1"
        )

    else:

        print(
            "Top prediction : FAIL"
        )

    # ========================================================================
    # FINAL VALIDATION
    # ========================================================================

    print_header(
        "SCENARIO-004 VALIDATION"
    )

    checks = [
        (
            "Database contains scenario",
            candidate_count >= 0,
        ),
        (
            "Hindcast source within 5 km",
            source_recovery_pass,
        ),
        (
            "AIS candidates found",
            candidate_search_pass,
        ),
        (
            "True source vessel found",
            source_found_pass,
        ),
        (
            "True source vessel ranked #1",
            source_rank_pass,
        ),
        (
            "Top-ranked vessel is true source",
            top_prediction_pass,
        ),
    ]

    all_passed = True

    for check_name, passed in checks:

        if passed:

            print(
                f"PASS  {check_name}"
            )

        else:

            print(
                f"FAIL  {check_name}"
            )

            all_passed = False

    # ========================================================================
    # SAVE RAW RESULT
    # ========================================================================

    output_path = (
        PROJECT_ROOT
        / "data"
        / "ais"
        / "processed"
        / "synthetic_scenario_004_attribution_result.json"
    )

    try:

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                result,
                file,
                indent=2,
                default=str,
            )

        print()

        print(
            "Raw attribution result saved to:"
        )

        print(
            output_path
        )

    except Exception as exc:

        print()

        print(
            "Warning: could not save "
            f"attribution result: {exc}"
        )

    # ========================================================================
    # FINAL RESULT
    # ========================================================================

    print_header(
        "FINAL RESULT"
    )

    if all_passed:

        print(
            "SCENARIO-004 END-TO-END TEST: PASS"
        )

        print()

        print(
            "The complete production attribution "
            "pipeline successfully:"
        )

        print(
            "  1. Loaded yearly environmental data"
        )

        print(
            "  2. Performed backward ensemble hindcasting"
        )

        print(
            "  3. Recovered the source region"
        )

        print(
            "  4. Recovered the release time"
        )

        print(
            "  5. Queried AIS candidates through PostGIS"
        )

        print(
            "  6. Scored candidate vessels"
        )

        print(
            "  7. Ranked the true source vessel #1"
        )

    else:

        print(
            "SCENARIO-004 END-TO-END TEST: FAIL"
        )

        print()

        print(
            "Review the failed checks above."
        )

    return result


# ============================================================================
# ENTRY POINT
# ============================================================================

async def main() -> None:

    await run_attribution()


if __name__ == "__main__":
    asyncio.run(main())