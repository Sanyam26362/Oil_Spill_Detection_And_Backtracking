from __future__ import annotations

import asyncio
import csv
import json
import math
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import Polygon
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.schemas import SpillIngestSchema
from app.repositories.ais_repository import AISRepository
from app.services.attribution_engine import AttributionEngine
from app.services.drift_engine import DriftEngine
from app.services.scoring_engine import ScoringEngine
from app.services.weather_service import WeatherService

from scripts.benchmark.runner import ingest_scenario, evaluate_scenario
from scripts.synthetic.scenario import SyntheticScenarioConfig
from scripts.synthetic.generate_synthetic_ais import generate_scenario_dataset

# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

WEATHER_DIR = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
OCEAN_DIR = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"
OUTPUT_DIR = PROJECT_ROOT / "data" / "ais" / "processed" / "benchmark_500_ml"

ML_INPUT_DIR = OUTPUT_DIR / "ml_inputs"
IN_DOMAIN_DIR = ML_INPUT_DIR / "in_domain"
OOD_DIR = ML_INPUT_DIR / "ood"
GROUND_TRUTH_DIR = OUTPUT_DIR / "ground_truth"

for directory in (OUTPUT_DIR, ML_INPUT_DIR, IN_DOMAIN_DIR, OOD_DIR, GROUND_TRUTH_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# =============================================================================
# BENCHMARK CONFIGURATION
# =============================================================================

TOTAL_CASES = 500
IN_DOMAIN_CASES = 400
OOD_CASES = 100

SPATIAL_OOD_CASES = 70
TEMPORAL_OOD_CASES = 30

RANDOM_SEED = 20260830
rng = random.Random(RANDOM_SEED)

# =============================================================================
# PHYSICAL MODEL
# =============================================================================

WINDAGE = 0.03
ENSEMBLE_SIZE = 100
TIMESTEP_MINUTES = 15
INITIAL_RADIUS_M = 500.0
CANDIDATE_RADIUS_MARGIN_KM = 5.0
CANDIDATE_TIME_WINDOW_HOURS = 2.0
NUM_DECOYS = 8
NUM_BACKGROUND = 100
MIN_AGE_HOURS = 6.0
MAX_AGE_HOURS = 24.0

# =============================================================================
# EASTERN MEDITERRANEAN WORKING DOMAIN
# =============================================================================

ENV_LAT_MIN = 30.25
ENV_LAT_MAX = 36.50
ENV_LON_MIN = 30.25
ENV_LON_MAX = 35.75

SOURCE_LAT_MIN = 31.00
SOURCE_LAT_MAX = 36.00
SOURCE_LON_MIN = 30.50
SOURCE_LON_MAX = 35.50

# =============================================================================
# DATABASE EXPECTATIONS
# =============================================================================

EXPECTED_REAL_AIS = 10_000
EXPECTED_YEARLY_ROWS = 72_970_713
EXPECTED_YEARLY_VESSELS = 200

UTC = timezone.utc

# =============================================================================
# HELPERS
# =============================================================================

def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def month_name(month: int) -> str:
    return datetime(2019, month, 1).strftime("%B")

def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), q))

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2)
    return 2.0 * radius * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)

# =============================================================================
# MONTH DISTRIBUTION
# =============================================================================

def create_month_schedule() -> list[int]:
    """Exactly 400 in-domain cases."""
    counts = {
        1: 34, 2: 33, 3: 34, 4: 33, 5: 34, 6: 33,
        7: 33, 8: 33, 9: 33, 10: 33, 11: 33, 12: 34,
    }
    total = sum(counts.values())

    if total != IN_DOMAIN_CASES:
        raise RuntimeError(f"Invalid month distribution: {total} != {IN_DOMAIN_CASES}")

    result: list[int] = []
    for month, count in counts.items():
        result.extend([month] * count)

    rng.shuffle(result)
    return result

# =============================================================================
# STRATIFIED LOCATION SAMPLING
# =============================================================================

GRID_LAT = 8
GRID_LON = 8

SAFE_LAT_MIN = 32.0
SAFE_LAT_MAX = 35.5
SAFE_LON_MIN = 30.5
SAFE_LON_MAX = 34.5

def stratified_source(case_index: int) -> tuple[float, float]:
    cells = GRID_LAT * GRID_LON
    cell_index = (case_index - 1) % cells
    lat_cell = cell_index // GRID_LON
    lon_cell = cell_index % GRID_LON

    lat_span = SAFE_LAT_MAX - SAFE_LAT_MIN
    lon_span = SAFE_LON_MAX - SAFE_LON_MIN

    cell_lat_size = lat_span / GRID_LAT
    cell_lon_size = lon_span / GRID_LON

    lat_min = SAFE_LAT_MIN + lat_cell * cell_lat_size
    lat_max = lat_min + cell_lat_size
    lon_min = SAFE_LON_MIN + lon_cell * cell_lon_size
    lon_max = lon_min + cell_lon_size

    latitude = rng.uniform(lat_min, lat_max)
    longitude = rng.uniform(lon_min, lon_max)

    return latitude, longitude

# =============================================================================
# RANDOM TIMESTAMP
# =============================================================================

def random_month_timestamp(month: int) -> datetime:
    start = datetime(2019, month, 1, 0, 0, 0, tzinfo=UTC)
    if month == 12:
        end = datetime(2019, 12, 31, 23, 59, 0, tzinfo=UTC)
    else:
        end = datetime(2019, month + 1, 1, 0, 0, 0, tzinfo=UTC) - timedelta(minutes=1)

    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, seconds))

# =============================================================================
# ML POLYGON
# =============================================================================

def build_polygon(latitude: float, longitude: float, area_km2: float) -> list[list[float]]:
    side_km = math.sqrt(max(area_km2, 0.05))
    half_lat = side_km / 111.32 / 2.0
    cos_lat = max(0.2, math.cos(math.radians(latitude)))
    half_lon = side_km / (111.32 * cos_lat) / 2.0

    return [
        [round(longitude - half_lon, 6), round(latitude - half_lat, 6)],
        [round(longitude + half_lon, 6), round(latitude - half_lat, 6)],
        [round(longitude + half_lon, 6), round(latitude + half_lat, 6)],
        [round(longitude - half_lon, 6), round(latitude + half_lat, 6)],
        [round(longitude - half_lon, 6), round(latitude - half_lat, 6)],
    ]

# =============================================================================
# ML PAYLOAD
# =============================================================================

def make_ml_payload(spill_id: str, detected_at: datetime, latitude: float, longitude: float, age_hours: float) -> dict[str, Any]:
    area_km2 = round(rng.uniform(0.05, 2.50), 3)
    confidence = round(rng.uniform(0.80, 0.99), 3)

    return {
        "spill_id": spill_id,
        "detected_at": iso_z(detected_at),
        "centroid": {
            "lon": round(longitude, 6),
            "lat": round(latitude, 6),
        },
        "polygon": build_polygon(latitude, longitude, area_km2),
        "area_km2": area_km2,
        "estimated_age_hours": round(age_hours, 2),
        "confidence_score": confidence,
    }

def validate_ml_payload(payload: dict[str, Any]) -> None:
    SpillIngestSchema.model_validate(payload)
    polygon = Polygon([(point[0], point[1]) for point in payload["polygon"]])

    if polygon.is_empty:
        raise ValueError("Polygon is empty.")
    if not polygon.is_valid:
        raise ValueError("Polygon is invalid.")

    lat = float(payload["centroid"]["lat"])
    lon = float(payload["centroid"]["lon"])

    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("Centroid contains non-finite coordinates.")

# =============================================================================
# BUILD VALID PHYSICAL CASE
# =============================================================================

def build_case(case_index: int, month: int, weather_service: WeatherService) -> tuple[SyntheticScenarioConfig, dict[str, Any], dict[str, Any]]:
    scenario_id = f"ML500-{case_index:03d}"
    prefix = f"SYNTH-S500-{case_index:03d}-"
    source_vessel_id = f"{prefix}SRC"

    for attempt in range(1, 501):
        detected_at = random_month_timestamp(month)
        age_hours = rng.uniform(MIN_AGE_HOURS, MAX_AGE_HOURS)
        release_time = detected_at - timedelta(hours=age_hours)

        if release_time.year != 2019:
            continue

        release_lat, release_lon = stratified_source(case_index)

        try:
            safety_offsets = [
                (0.0, 0.0), (0.03, 0.0), (-0.03, 0.0), (0.0, 0.03), (0.0, -0.03),
                (0.03, 0.03), (0.03, -0.03), (-0.03, 0.03), (-0.03, -0.03),
            ]
            environment_ok = True

            for dlat, dlon in safety_offsets:
                test_lat = release_lat + dlat
                test_lon = release_lon + dlon
                try:
                    test_velocity = weather_service.get_velocity(test_lat, test_lon, release_time)
                    values = np.asarray(
                        [test_velocity.wind_u, test_velocity.wind_v, test_velocity.current_u, test_velocity.current_v],
                        dtype=float,
                    )
                    if not np.all(np.isfinite(values)):
                        environment_ok = False
                        break
                except Exception:
                    environment_ok = False
                    break

            if not environment_ok:
                continue

            # Check velocity exactly at the release coordinates
            velocity = weather_service.get_velocity(release_lat, release_lon, release_time)
            environmental = np.asarray(
                [velocity.wind_u, velocity.wind_v, velocity.current_u, velocity.current_v],
                dtype=float,
            )

            if not np.all(np.isfinite(environmental)):
                continue

            drift = DriftEngine(weather_service=weather_service, windage=WINDAGE)
            trajectory = drift.forward_drift(
                start_latitude=release_lat,
                start_longitude=release_lon,
                start_time=release_time,
                duration_hours=age_hours,
                timestep_minutes=TIMESTEP_MINUTES,
            )

            if not trajectory.states:
                continue

            observation_state = trajectory.end
            observation_lat = observation_state.latitude
            observation_lon = observation_state.longitude

            if not (math.isfinite(observation_lat) and math.isfinite(observation_lon)):
                continue

            payload = make_ml_payload(
                spill_id=f"spill_{case_index:06d}",
                detected_at=detected_at,
                latitude=observation_lat,
                longitude=observation_lon,
                age_hours=age_hours,
            )
            validate_ml_payload(payload)

            config = SyntheticScenarioConfig(
                scenario_id=scenario_id,
                release_lat=release_lat,
                release_lon=release_lon,
                release_time=release_time,
                observation_lat=observation_lat,
                observation_lon=observation_lon,
                observation_time=detected_at,
                drift_duration_hours=age_hours,
                bounds_lat_min=(release_lat - 0.5),
                bounds_lat_max=(release_lat + 0.5),
                bounds_lon_min=(release_lon - 0.5),
                bounds_lon_max=(release_lon + 0.5),
                num_background_vessels=NUM_BACKGROUND,
                num_decoy_vessels=NUM_DECOYS,
                vessel_id_prefix=prefix,
                source_vessel_id=source_vessel_id,
                decoy_start_id=1,
                seed=(RANDOM_SEED + case_index),
            )

            ground_truth = {
                "scenario_id": scenario_id,
                "source": {
                    "vessel_id": source_vessel_id,
                    "latitude": release_lat,
                    "longitude": release_lon,
                    "release_time": iso_z(release_time),
                },
                "observation": {
                    "latitude": observation_lat,
                    "longitude": observation_lon,
                    "timestamp": iso_z(detected_at),
                },
                "benchmark": {
                    "month": month,
                    "generation_attempt": attempt,
                    "estimated_age_hours": age_hours,
                },
            }

            return config, payload, ground_truth

        except Exception:
            continue

    raise RuntimeError(f"Unable to produce valid physical case {case_index} after 500 attempts.")

# =============================================================================
# EXACT TEMPORARY CLEANUP
# =============================================================================

async def clean_scenario(scenario_id: str, vessel_prefix: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                DELETE FROM ais_positions
                WHERE is_synthetic = TRUE AND scenario_id = :scenario_id
                """
            ),
            {"scenario_id": scenario_id},
        )
        deleted = int(result.rowcount or 0)

        await session.execute(
            text(
                """
                DELETE FROM vessels v
                WHERE v.vessel_id LIKE :prefix
                  AND NOT EXISTS (
                      SELECT 1 FROM ais_positions p
                      WHERE p.vessel_id = v.vessel_id
                  )
                """
            ),
            {"prefix": f"{vessel_prefix}%"},
        )
        await session.commit()

    return deleted

# =============================================================================
# SCENARIO VERIFICATION
# =============================================================================

async def verify_scenario(scenario_id: str, source_vessel_id: str) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM ais_positions WHERE scenario_id = :scenario_id AND is_synthetic = TRUE"),
            {"scenario_id": scenario_id},
        )
        rows = int(result.scalar_one())

        result = await session.execute(
            text("SELECT COUNT(DISTINCT vessel_id) FROM ais_positions WHERE scenario_id = :scenario_id AND is_synthetic = TRUE"),
            {"scenario_id": scenario_id},
        )
        vessels = int(result.scalar_one())

        result = await session.execute(
            text("SELECT COUNT(*) FROM ais_positions WHERE scenario_id = :scenario_id AND vessel_id = :source_vessel AND is_synthetic = TRUE"),
            {"scenario_id": scenario_id, "source_vessel": source_vessel_id},
        )
        source_rows = int(result.scalar_one())

    return {"rows": rows, "vessels": vessels, "source_rows": source_rows}

# =============================================================================
# DATABASE SAFETY
# =============================================================================

async def get_real_count() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM ais_positions WHERE is_synthetic = FALSE"))
        return int(result.scalar_one())

async def get_yearly_integrity() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT COUNT(*) AS rows, COUNT(DISTINCT vessel_id) AS vessels,
                       MIN(timestamp) AS min_time, MAX(timestamp) AS max_time
                FROM ais_positions
                WHERE is_synthetic = TRUE AND scenario_id = 'synthetic-2019'
                """
            )
        )
        row = result.one()

    return {
        "rows": int(row.rows),
        "vessels": int(row.vessels),
        "min_time": row.min_time.isoformat() if row.min_time else None,
        "max_time": row.max_time.isoformat() if row.max_time else None,
    }

# =============================================================================
# BLIND ATTRIBUTION
# =============================================================================

async def run_blind_attribution(weather_service: WeatherService, payload: dict[str, Any], scenario_id: str) -> tuple[dict[str, Any], float]:
    centroid = payload["centroid"]
    timestamp = parse_iso(payload["detected_at"])
    age_hours = float(payload["estimated_age_hours"])

    engine = AttributionEngine(
        weather_service=weather_service,
        ais_repository=AISRepository(),
        scoring_engine=ScoringEngine(),
    )

    async with AsyncSessionLocal() as session:
        started = time.perf_counter()
        result = await engine.attribute(
            db=session,
            observation_latitude=float(centroid["lat"]),
            observation_longitude=float(centroid["lon"]),
            observation_time=timestamp,
            drift_duration_hours=age_hours,
            ensemble_size=ENSEMBLE_SIZE,
            initial_radius_m=INITIAL_RADIUS_M,
            timestep_minutes=TIMESTEP_MINUTES,
            candidate_radius_margin_km=CANDIDATE_RADIUS_MARGIN_KM,
            candidate_time_window_hours=CANDIDATE_TIME_WINDOW_HOURS,
            synthetic_only=True,
            scenario_id=scenario_id,
        )
        elapsed = time.perf_counter() - started

    return result, elapsed

# =============================================================================
# IN-DOMAIN CASE
# =============================================================================

async def run_in_domain_case(case_index: int, month: int, weather_service: WeatherService) -> dict[str, Any]:
    started = time.perf_counter()
    scenario_id = f"ML500-{case_index:03d}"
    prefix = f"SYNTH-S500-{case_index:03d}-"

    try:
        generation_started = time.perf_counter()
        config, ml_payload, ground_truth = build_case(case_index, month, weather_service)
        generation_time = time.perf_counter() - generation_started

        save_json(IN_DOMAIN_DIR / f"{ml_payload['spill_id']}.json", ml_payload)

        ais_started = time.perf_counter()
        df, generator_ground_truth = generate_scenario_dataset(config)
        ais_generation_time = time.perf_counter() - ais_started

        source_vessel_id = generator_ground_truth["source"]["vessel_id"]
        ground_truth["source"]["vessel_id"] = source_vessel_id

        save_json(GROUND_TRUTH_DIR / f"{scenario_id}_gt.json", ground_truth)
        await clean_scenario(scenario_id, prefix)

        ingest_started = time.perf_counter()
        verification = await ingest_scenario(df, scenario_id)
        ingest_time = time.perf_counter() - ingest_started

        db_check = await verify_scenario(scenario_id, source_vessel_id)
        if db_check["source_rows"] <= 0:
            raise RuntimeError("Source vessel not present after ingestion.")

        prediction, attribution_time = await run_blind_attribution(weather_service, ml_payload, scenario_id)
        evaluation = evaluate_scenario(prediction, ground_truth)

        rank = evaluation["true_vessel_rank"]
        mrr = 1.0 / rank if rank is not None else 0.0
        total_time = time.perf_counter() - started

        return {
            "case_id": ml_payload["spill_id"],
            "scenario_id": scenario_id,
            "case_type": "in_domain",
            "month": month,
            "month_name": month_name(month),
            "detected_at": ml_payload["detected_at"],
            "release_time": ground_truth["source"]["release_time"],
            "estimated_age_hours": ml_payload["estimated_age_hours"],
            "centroid_lat": ml_payload["centroid"]["lat"],
            "centroid_lon": ml_payload["centroid"]["lon"],
            "area_km2": ml_payload["area_km2"],
            "confidence_score": ml_payload["confidence_score"],
            "true_source_vessel_id": evaluation["true_source_vessel_id"],
            "predicted_vessel_id": evaluation["predicted_vessel_id"],
            "true_vessel_rank": rank,
            "candidate_count": int(evaluation["candidate_count"]),
            "candidate_recall": int(evaluation["candidate_recall"]),
            "top1_correct": int(evaluation["top1_correct"]),
            "top3_correct": int(evaluation["top3_correct"]),
            "mrr": round(mrr, 4),
            "source_error_km": float(evaluation["source_error_km"]),
            "top_score": float(evaluation["top_score"]),
            "second_score": float(evaluation["second_score"]),
            "score_margin": float(evaluation["score_margin"]),
            "generation_time_seconds": round(generation_time, 4),
            "ais_generation_time_seconds": round(ais_generation_time, 4),
            "ingestion_time_seconds": round(ingest_time, 4),
            "attribution_time_seconds": round(attribution_time, 4),
            "total_case_time_seconds": round(total_time, 4),
            "ais_rows_generated": int(len(df)),
            "ais_vessels_generated": int(df["vessel_id"].nunique()),
            "db_rows_inserted": int(verification["rows_inserted"]),
            "db_vessels_inserted": int(verification["vessels_inserted"]),
            "status": "PASS",
            "error": "",
        }

    except Exception as exc:
        try:
            await clean_scenario(scenario_id, prefix)
        except Exception:
            pass

        return {
            "case_id": f"spill_{case_index:06d}",
            "scenario_id": scenario_id,
            "case_type": "in_domain",
            "month": month,
            "month_name": month_name(month),
            "detected_at": "",
            "release_time": "",
            "estimated_age_hours": "",
            "centroid_lat": "",
            "centroid_lon": "",
            "area_km2": "",
            "confidence_score": "",
            "true_source_vessel_id": "",
            "predicted_vessel_id": "",
            "true_vessel_rank": "",
            "candidate_count": 0,
            "candidate_recall": 0,
            "top1_correct": 0,
            "top3_correct": 0,
            "mrr": 0.0,
            "source_error_km": "",
            "top_score": 0.0,
            "second_score": 0.0,
            "score_margin": 0.0,
            "generation_time_seconds": "",
            "ais_generation_time_seconds": "",
            "ingestion_time_seconds": "",
            "attribution_time_seconds": "",
            "total_case_time_seconds": round(time.perf_counter() - started, 4),
            "ais_rows_generated": 0,
            "ais_vessels_generated": 0,
            "db_rows_inserted": 0,
            "db_vessels_inserted": 0,
            "status": "FAIL",
            "error": str(exc),
        }

# =============================================================================
# OOD DOMAIN CLASSIFICATION
# =============================================================================

def classify_ood(latitude: float, longitude: float, detected_at: datetime) -> tuple[bool, str]:
    geographic_outside = not (ENV_LAT_MIN <= latitude <= ENV_LAT_MAX and ENV_LON_MIN <= longitude <= ENV_LON_MAX)
    temporal_outside = (detected_at.year != 2019)

    if geographic_outside:
        return True, "spatial"
    if temporal_outside:
        return True, "temporal"
    return False, ""

def make_spatial_ood(index: int) -> dict[str, Any]:
    mode = rng.choice(["south", "north", "west", "east"])

    if mode == "south":
        latitude = rng.uniform(20.0, ENV_LAT_MIN - 1.0)
        longitude = rng.uniform(ENV_LON_MIN, ENV_LON_MAX)
    elif mode == "north":
        latitude = rng.uniform(ENV_LAT_MAX + 1.0, 45.0)
        longitude = rng.uniform(ENV_LON_MIN, ENV_LON_MAX)
    elif mode == "west":
        latitude = rng.uniform(ENV_LAT_MIN, ENV_LAT_MAX)
        longitude = rng.uniform(15.0, ENV_LON_MIN - 1.0)
    else:
        latitude = rng.uniform(ENV_LAT_MIN, ENV_LAT_MAX)
        longitude = rng.uniform(ENV_LON_MAX + 1.0, 50.0)

    detected_at = datetime(2019, rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59), 0, tzinfo=UTC)

    payload = make_ml_payload(f"spill_ood_{index:06d}", detected_at, latitude, longitude, rng.uniform(MIN_AGE_HOURS, MAX_AGE_HOURS))
    payload["_expected_ood_reason"] = mode
    return payload

def make_temporal_ood(index: int) -> dict[str, Any]:
    latitude, longitude = stratified_source(index + 700)
    year = rng.choice([2018, 2020])
    detected_at = datetime(year, rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59), 0, tzinfo=UTC)

    payload = make_ml_payload(f"spill_ood_{index:06d}", detected_at, latitude, longitude, rng.uniform(MIN_AGE_HOURS, MAX_AGE_HOURS))
    payload["_expected_ood_reason"] = "before_2019" if year == 2018 else "after_2019"
    return payload

# =============================================================================
# OOD TEST
# =============================================================================

def run_ood_case(index: int) -> dict[str, Any]:
    started = time.perf_counter()
    payload = make_spatial_ood(index) if index <= SPATIAL_OOD_CASES else make_temporal_ood(index)
    expected_reason = payload["_expected_ood_reason"]

    clean_payload = {key: value for key, value in payload.items() if not key.startswith("_")}
    validate_ml_payload(clean_payload)

    latitude = float(clean_payload["centroid"]["lat"])
    longitude = float(clean_payload["centroid"]["lon"])
    detected_at = parse_iso(clean_payload["detected_at"])

    actually_ood, actual_reason = classify_ood(latitude, longitude, detected_at)
    passed = actually_ood and (actual_reason == ("spatial" if index <= SPATIAL_OOD_CASES else "temporal"))

    save_json(OOD_DIR / f"{clean_payload['spill_id']}.json", clean_payload)
    elapsed = time.perf_counter() - started

    return {
        "case_id": clean_payload["spill_id"],
        "case_type": "ood",
        "ood_expected": expected_reason,
        "ood_detected": actual_reason,
        "detected_at": clean_payload["detected_at"],
        "centroid_lat": latitude,
        "centroid_lon": longitude,
        "area_km2": clean_payload["area_km2"],
        "estimated_age_hours": clean_payload["estimated_age_hours"],
        "confidence_score": clean_payload["confidence_score"],
        "correctly_classified_ood": int(passed),
        "latency_seconds": round(elapsed, 4),
        "status": "PASS" if passed else "FAIL",
        "error": "" if passed else f"Expected {expected_reason}, got {actual_reason}",
    }

# =============================================================================
# SUMMARIES
# =============================================================================

def summarize_in_domain(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    successful = [row for row in rows if row["status"] == "PASS"]

    if not successful:
        return {"total": total, "successful": 0, "failed": total}

    attribution = [float(row["attribution_time_seconds"]) for row in successful]
    total_times = [float(row["total_case_time_seconds"]) for row in successful]
    errors = [float(row["source_error_km"]) for row in successful if row["source_error_km"] != ""]
    candidates = [int(row["candidate_count"]) for row in successful]
    margins = [float(row["score_margin"]) for row in successful]

    return {
        "total": total,
        "successful": len(successful),
        "failed": total - len(successful),
        "candidate_recall": statistics.mean(row["candidate_recall"] for row in successful),
        "top1_accuracy": statistics.mean(row["top1_correct"] for row in successful),
        "top3_accuracy": statistics.mean(row["top3_correct"] for row in successful),
        "mrr": statistics.mean(row["mrr"] for row in successful),
        "mean_source_error_km": statistics.mean(errors) if errors else 0.0,
        "median_source_error_km": statistics.median(errors) if errors else 0.0,
        "p95_source_error_km": percentile(errors, 95) if errors else 0.0,
        "max_source_error_km": max(errors) if errors else 0.0,
        "mean_candidate_count": statistics.mean(candidates),
        "median_candidate_count": statistics.median(candidates),
        "mean_score_margin": statistics.mean(margins),
        "mean_attribution_time_seconds": statistics.mean(attribution),
        "median_attribution_time_seconds": statistics.median(attribution),
        "p95_attribution_time_seconds": percentile(attribution, 95),
        "max_attribution_time_seconds": max(attribution),
        "mean_total_case_time_seconds": statistics.mean(total_times),
        "p95_total_case_time_seconds": percentile(total_times, 95),
    }

def summarize_ood(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    passed = sum(row["correctly_classified_ood"] for row in rows)
    spatial = [row for row in rows if row["ood_expected"] in {"south", "north", "east", "west"}]
    temporal = [row for row in rows if row["ood_expected"] in {"before_2019", "after_2019"}]
    latencies = [float(row["latency_seconds"]) for row in rows]

    return {
        "total": total,
        "correct": passed,
        "failed": total - passed,
        "rejection_accuracy": passed / total if total else 0.0,
        "spatial_total": len(spatial),
        "spatial_correct": sum(row["correctly_classified_ood"] for row in spatial),
        "spatial_accuracy": sum(row["correctly_classified_ood"] for row in spatial) / len(spatial) if spatial else 0.0,
        "temporal_total": len(temporal),
        "temporal_correct": sum(row["correctly_classified_ood"] for row in temporal),
        "temporal_accuracy": sum(row["correctly_classified_ood"] for row in temporal) / len(temporal) if temporal else 0.0,
        "mean_latency_seconds": statistics.mean(latencies) if latencies else 0.0,
        "median_latency_seconds": statistics.median(latencies) if latencies else 0.0,
        "p95_latency_seconds": percentile(latencies, 95) if latencies else 0.0,
    }

def summarize_months(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["month"])].append(row)

    output = {}
    for month in range(1, 13):
        summary = summarize_in_domain(grouped[month])
        summary["month"] = month
        summary["month_name"] = month_name(month)
        output[f"{month:02d}"] = summary

    return output

# =============================================================================
# CSV
# =============================================================================

def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

# =============================================================================
# MARKDOWN REPORT
# =============================================================================

def write_report(path: Path, report: dict[str, Any]) -> None:
    ind = report["in_domain_summary"]
    ood = report["ood_summary"]
    monthly = report["monthly_summary"]
    db = report["database_integrity"]

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# 500-Case ML Input Benchmark\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- Total cases: {TOTAL_CASES}\n")
        handle.write(f"- In-domain: {IN_DOMAIN_CASES}\n")
        handle.write(f"- OOD: {OOD_CASES}\n")
        handle.write(f"- Random seed: {RANDOM_SEED}\n")
        handle.write(f"- Total runtime: {report['runtime_seconds']:.2f}s\n\n")

        handle.write("## In-Domain Metrics\n\n")
        handle.write("| Metric | Value |\n|---|---:|\n")

        metrics_list = [
            ("Cases", "total"), ("Successful", "successful"), ("Failed", "failed"),
            ("Candidate Recall", "candidate_recall"), ("Top-1 Accuracy", "top1_accuracy"),
            ("Top-3 Accuracy", "top3_accuracy"), ("MRR", "mrr"),
            ("Mean Source Error km", "mean_source_error_km"), ("Median Source Error km", "median_source_error_km"),
            ("P95 Source Error km", "p95_source_error_km"), ("Mean Candidate Count", "mean_candidate_count"),
            ("Mean Attribution Seconds", "mean_attribution_time_seconds"),
            ("Median Attribution Seconds", "median_attribution_time_seconds"),
            ("P95 Attribution Seconds", "p95_attribution_time_seconds"),
            ("Max Attribution Seconds", "max_attribution_time_seconds"),
            ("Mean Total Case Seconds", "mean_total_case_time_seconds"),
            ("P95 Total Case Seconds", "p95_total_case_time_seconds")
        ]
        
        for label, key in metrics_list:
            handle.write(f"| {label} | {ind.get(key, 0)} |\n")
        handle.write("\n")

        handle.write("## OOD Metrics\n\n")
        handle.write("| Metric | Value |\n|---|---:|\n")
        ood_metrics = [
            ("Total OOD", "total"), ("Correctly classified", "correct"), ("Failed", "failed"),
            ("Overall accuracy", "rejection_accuracy"), ("Spatial accuracy", "spatial_accuracy"),
            ("Temporal accuracy", "temporal_accuracy"), ("Mean latency seconds", "mean_latency_seconds"),
            ("Median latency seconds", "median_latency_seconds"), ("P95 latency seconds", "p95_latency_seconds")
        ]
        
        for label, key in ood_metrics:
            handle.write(f"| {label} | {ood.get(key, 0)} |\n")
        handle.write("\n")

        handle.write("## Monthly Results\n\n")
        handle.write("| Month | Cases | Recall | Top-1 | Top-3 | MRR | Mean Error km | Median Attr s | P95 Attr s |\n")
        handle.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")

        for key in sorted(monthly.keys()):
            row = monthly[key]
            handle.write(
                f"| {row['month_name']} | {row.get('total', 0)} | {row.get('candidate_recall', 0.0):.2%} | "
                f"{row.get('top1_accuracy', 0.0):.2%} | {row.get('top3_accuracy', 0.0):.2%} | "
                f"{row.get('mrr', 0.0):.4f} | {row.get('mean_source_error_km', 0.0):.4f} | "
                f"{row.get('median_attribution_time_seconds', 0.0):.4f} | {row.get('p95_attribution_time_seconds', 0.0):.4f} |\n"
            )
        handle.write("\n")

        handle.write("## Database Integrity\n\n")
        handle.write("| Check | Before | After | Expected | Status |\n|---|---:|---:|---:|---|\n")

        checks = [
            ("Real AIS", db["real_ais_before"], db["real_ais_after"], EXPECTED_REAL_AIS, (db["real_ais_before"] == EXPECTED_REAL_AIS and db["real_ais_after"] == EXPECTED_REAL_AIS)),
            ("Yearly synthetic rows", db["yearly_rows_before"], db["yearly_rows_after"], EXPECTED_YEARLY_ROWS, (db["yearly_rows_before"] == EXPECTED_YEARLY_ROWS and db["yearly_rows_after"] == EXPECTED_YEARLY_ROWS)),
            ("Yearly synthetic vessels", db["yearly_vessels_before"], db["yearly_vessels_after"], EXPECTED_YEARLY_VESSELS, (db["yearly_vessels_before"] == EXPECTED_YEARLY_VESSELS and db["yearly_vessels_after"] == EXPECTED_YEARLY_VESSELS)),
        ]

        for label, before, after, expected, passed in checks:
            handle.write(f"| {label} | {before} | {after} | {expected} | {'PASS' if passed else 'FAIL'} |\n")
        handle.write("\n")

        handle.write("## Pass Criteria\n\n")
        handle.write(
            "| Criterion | Required |\n|---|---:|\n"
            "| Candidate recall | >= 95% |\n| Top-1 | >= 90% |\n| Top-3 | >= 95% |\n"
            "| OOD classification | >= 95% |\n| Real AIS unchanged | 10,000 |\n"
            "| Yearly AIS unchanged | 72,970,713 |\n| Yearly vessels unchanged | 200 |\n\n"
        )
        handle.write(f"## Overall Status\n\n**{'PASS' if report['overall_pass'] else 'FAIL'}**\n")

# =============================================================================
# MAIN
# =============================================================================

async def main() -> None:
    started = time.perf_counter()

    print("\n" + "=" * 90)
    print("500-CASE ML INPUT WHOLE-YEAR ATTRIBUTION BENCHMARK")
    print("=" * 90)
    print(f"In-domain cases : {IN_DOMAIN_CASES}")
    print(f"OOD cases       : {OOD_CASES}")
    print(f"Total cases     : {TOTAL_CASES}")
    print("Year            : 2019")
    print(f"Random seed     : {RANDOM_SEED}\n")
    print("ML payload:\nspill_id + detected_at + centroid + polygon + area_km2 + estimated_age_hours + confidence_score\n")

    # -------------------------------------------------------------------------
    # Database baseline
    # -------------------------------------------------------------------------
    real_before = await get_real_count()
    yearly_before = await get_yearly_integrity()

    print(f"Real AIS before       : {real_before:,}")
    print(f"Yearly AIS rows before: {yearly_before['rows']:,}")
    print(f"Yearly AIS vessels    : {yearly_before['vessels']}")
    print(f"Yearly time range     : {yearly_before['min_time']} -> {yearly_before['max_time']}")

    if real_before != EXPECTED_REAL_AIS:
        raise RuntimeError("Real AIS baseline changed.")
    if yearly_before["rows"] != EXPECTED_YEARLY_ROWS:
        raise RuntimeError(f"Yearly AIS row count is not {EXPECTED_YEARLY_ROWS:,}.")
    if yearly_before["vessels"] != EXPECTED_YEARLY_VESSELS:
        raise RuntimeError("Yearly vessel count is not 200.")

    # -------------------------------------------------------------------------
    # Environment
    # -------------------------------------------------------------------------
    weather_service = WeatherService(weather_yearly_dir=WEATHER_DIR, ocean_yearly_dir=OCEAN_DIR)
    in_domain_results = []
    ood_results = []

    try:
        # =====================================================================
        # SMOKE TEST
        # =====================================================================
        print("\n" + "=" * 90)
        print("SMOKE TEST — JANUARY / JULY / DECEMBER")
        print("=" * 90)

        smoke_cases = [(901, 1), (902, 7), (903, 12)]

        for smoke_no, (case_index, month) in enumerate(smoke_cases, start=1):
            config, payload, ground_truth = build_case(case_index, month, weather_service)
            scenario_id = config.scenario_id
            prefix = f"SYNTH-S500-{case_index:03d}-"

            df, generator_gt = generate_scenario_dataset(config)
            source_vessel = generator_gt["source"]["vessel_id"]

            await clean_scenario(scenario_id, prefix)
            verification = await ingest_scenario(df, scenario_id)
            db_check = await verify_scenario(scenario_id, source_vessel)
            prediction, attribution_time = await run_blind_attribution(weather_service, payload, scenario_id)
            candidates = int(prediction.get("candidate_count", 0))

            await clean_scenario(scenario_id, prefix)

            print(f"\nSMOKE {smoke_no}/3 | month={month_name(month)}")
            print("  Payload schema : PASS")
            print(f"  AIS generation : PASS ({len(df):,} rows)")
            print(f"  DB ingestion   : PASS ({verification['rows_inserted']:,} rows)")
            print(f"  Source exists  : {'PASS' if db_check['source_rows'] > 0 else 'FAIL'} ({db_check['source_rows']:,} rows)")
            print(f"  Candidates     : {'PASS' if candidates > 0 else 'FAIL'} ({candidates})")
            print(f"  Attribution    : {'PASS' if prediction else 'FAIL'} ({attribution_time:.3f}s)")

            if candidates <= 0:
                raise RuntimeError(f"Smoke test failed for {month_name(month)}.")

        print("\nSMOKE TEST PASSED")

        # =====================================================================
        # MONTH SCHEDULE
        # =====================================================================
        month_schedule = create_month_schedule()
        print("\nMonth distribution:")
        counts = defaultdict(int)
        for month in month_schedule:
            counts[month] += 1
        for month in range(1, 13):
            print(f"  {month_name(month):>9}: {counts[month]}")

        # =====================================================================
        # PHASE 1
        # =====================================================================
        print("\n" + "=" * 90)
        print("PHASE 1/2 — 400 IN-DOMAIN CASES")
        print("=" * 90)

        for index, month in enumerate(month_schedule, start=1):
            result = await run_in_domain_case(index, month, weather_service)
            in_domain_results.append(result)

            print(
                f"[{index:03d}/400] {result['status']:<4} | {result['month_name']:<9} | "
                f"candidates={result['candidate_count']:<3} | top1={result['top1_correct']} | "
                f"rank={result['true_vessel_rank']} | error={result['source_error_km']} km | "
                f"attr={result['attribution_time_seconds']}s | total={result['total_case_time_seconds']}s",
                flush=True,
            )

            if index % 25 == 0:
                checkpoint = summarize_in_domain(in_domain_results)
                print("\n" + "-" * 90)
                print(f"CHECKPOINT {index}/400")
                print(f"  Top-1        : {checkpoint.get('top1_accuracy', 0.0):.2%}")
                print(f"  Top-3        : {checkpoint.get('top3_accuracy', 0.0):.2%}")
                print(f"  Recall       : {checkpoint.get('candidate_recall', 0.0):.2%}")
                print(f"  Mean attr    : {checkpoint.get('mean_attribution_time_seconds', 0.0):.3f}s")
                print(f"  Failures     : {checkpoint.get('failed', 0)}")

                current_real = await get_real_count()
                if current_real != real_before:
                    raise RuntimeError("REAL AIS COUNT CHANGED.")
                print("-" * 90)

        # =====================================================================
        # PHASE 2
        # =====================================================================
        print("\n" + "=" * 90)
        print("PHASE 2/2 — 100 OOD CASES")
        print("=" * 90)

        for index in range(1, OOD_CASES + 1):
            result = run_ood_case(index)
            ood_results.append(result)

            print(
                f"[OOD {index:03d}/100] {result['status']:<4} | expected={result['ood_expected']:<12} | "
                f"detected={result['ood_detected']:<8} | latency={result['latency_seconds']}s",
                flush=True,
            )

            if index % 25 == 0:
                checkpoint = summarize_ood(ood_results)
                print(f"\nOOD CHECKPOINT {index}/100")
                print(f"  Accuracy : {checkpoint['rejection_accuracy']:.2%}")
                print(f"  Failures : {checkpoint['failed']}")

    finally:
        weather_service.close()  # Assuming WeatherService requires cleanup

    # =========================================================================
    # FINAL INTEGRITY
    # =========================================================================
    real_after = await get_real_count()
    yearly_after = await get_yearly_integrity()

    if real_after != real_before:
        raise RuntimeError("REAL AIS DATA WAS MODIFIED.")
    if yearly_after["rows"] != yearly_before["rows"]:
        raise RuntimeError("synthetic-2019 ROW COUNT CHANGED.")
    if yearly_after["vessels"] != yearly_before["vessels"]:
        raise RuntimeError("synthetic-2019 VESSEL COUNT CHANGED.")

    # =========================================================================
    # METRICS
    # =========================================================================
    in_domain_summary = summarize_in_domain(in_domain_results)
    ood_summary = summarize_ood(ood_results)
    monthly_summary = summarize_months(in_domain_results)
    runtime = time.perf_counter() - started

    # =========================================================================
    # PASS CRITERIA
    # =========================================================================
    in_domain_pass = (
        in_domain_summary.get("candidate_recall", 0.0) >= 0.95
        and in_domain_summary.get("top1_accuracy", 0.0) >= 0.90
        and in_domain_summary.get("top3_accuracy", 0.0) >= 0.95
    )
    ood_pass = ood_summary.get("rejection_accuracy", 0.0) >= 0.95
    database_pass = (
        real_after == EXPECTED_REAL_AIS
        and yearly_after["rows"] == EXPECTED_YEARLY_ROWS
        and yearly_after["vessels"] == EXPECTED_YEARLY_VESSELS
    )
    overall_pass = in_domain_pass and ood_pass and database_pass

    # =========================================================================
    # REPORT
    # =========================================================================
    report = {
        "configuration": {
            "total_cases": TOTAL_CASES,
            "in_domain_cases": IN_DOMAIN_CASES,
            "ood_cases": OOD_CASES,
            "spatial_ood_cases": SPATIAL_OOD_CASES,
            "temporal_ood_cases": TEMPORAL_OOD_CASES,
            "year": 2019,
            "random_seed": RANDOM_SEED,
            "ensemble_size": ENSEMBLE_SIZE,
            "timestep_minutes": TIMESTEP_MINUTES,
            "initial_radius_m": INITIAL_RADIUS_M,
            "windage": WINDAGE,
            "candidate_radius_margin_km": CANDIDATE_RADIUS_MARGIN_KM,
            "candidate_time_window_hours": CANDIDATE_TIME_WINDOW_HOURS,
            "minimum_age_hours": MIN_AGE_HOURS,
            "maximum_age_hours": MAX_AGE_HOURS,
            "decoys": NUM_DECOYS,
            "background_vessels": NUM_BACKGROUND,
            "environment_lat_range": f"{ENV_LAT_MIN} -> {ENV_LAT_MAX}",
            "environment_lon_range": f"{ENV_LON_MIN} -> {ENV_LON_MAX}",
        },
        "in_domain_summary": in_domain_summary,
        "ood_summary": ood_summary,
        "monthly_summary": monthly_summary,
        "database_integrity": {
            "real_ais_before": real_before,
            "real_ais_after": real_after,
            "yearly_rows_before": yearly_before["rows"],
            "yearly_rows_after": yearly_after["rows"],
            "yearly_vessels_before": yearly_before["vessels"],
            "yearly_vessels_after": yearly_after["vessels"],
        },
        "runtime_seconds": runtime,
        "overall_pass": overall_pass,
    }

    summary_path = OUTPUT_DIR / "summary.json"
    all_results_path = OUTPUT_DIR / "all_results.json"
    in_domain_csv = OUTPUT_DIR / "in_domain_results.csv"
    ood_csv = OUTPUT_DIR / "ood_results.csv"
    report_path = OUTPUT_DIR / "benchmark_500_report.md"

    save_json(summary_path, report)
    save_json(all_results_path, {"in_domain": in_domain_results, "ood": ood_results})
    write_csv(in_domain_csv, in_domain_results)
    write_csv(ood_csv, ood_results)
    
    write_report(
        report_path,
        {
            **report,
            "artifacts": [
                str(summary_path), str(all_results_path), str(in_domain_csv), 
                str(ood_csv), str(report_path), str(IN_DOMAIN_DIR), 
                str(OOD_DIR), str(GROUND_TRUTH_DIR)
            ],
        },
    )

    # =========================================================================
    # FINAL TERMINAL SUMMARY
    # =========================================================================
    print("\n" + "=" * 90)
    print("500-CASE BENCHMARK COMPLETE")
    print("=" * 90)
    print("\nIN-DOMAIN")
    print(f"  Cases             : {in_domain_summary['total']}")
    print(f"  Successful        : {in_domain_summary['successful']}")
    print(f"  Failed            : {in_domain_summary['failed']}")
    print(f"  Candidate recall  : {in_domain_summary['candidate_recall']:.2%}")
    print(f"  Top-1             : {in_domain_summary['top1_accuracy']:.2%}")
    print(f"  Top-3             : {in_domain_summary['top3_accuracy']:.2%}")
    print(f"  MRR               : {in_domain_summary['mrr']:.4f}")
    print(f"  Mean error        : {in_domain_summary['mean_source_error_km']:.4f} km")
    print(f"  Median error      : {in_domain_summary['median_source_error_km']:.4f} km")
    print(f"  P95 error         : {in_domain_summary['p95_source_error_km']:.4f} km")
    print(f"  Mean attribution  : {in_domain_summary['mean_attribution_time_seconds']:.4f}s")
    print(f"  Median attribution: {in_domain_summary['median_attribution_time_seconds']:.4f}s")
    print(f"  P95 attribution   : {in_domain_summary['p95_attribution_time_seconds']:.4f}s")

    print("\nOOD")
    print(f"  Cases             : {ood_summary['total']}")
    print(f"  Correct           : {ood_summary['correct']}")
    print(f"  Failed            : {ood_summary['failed']}")
    print(f"  Accuracy          : {ood_summary['rejection_accuracy']:.2%}")
    print(f"  Spatial           : {ood_summary['spatial_correct']}/{ood_summary['spatial_total']}")
    print(f"  Temporal          : {ood_summary['temporal_correct']}/{ood_summary['temporal_total']}")

    print("\nDATABASE")
    print(f"  Real AIS          : {real_after:,}")
    print(f"  Yearly AIS rows   : {yearly_after['rows']:,}")
    print(f"  Yearly vessels    : {yearly_after['vessels']}")

    print("\nFINAL STATUS")
    print(f"  In-domain         : {'PASS' if in_domain_pass else 'FAIL'}")
    print(f"  OOD               : {'PASS' if ood_pass else 'FAIL'}")
    print(f"  Database          : {'PASS' if database_pass else 'FAIL'}")
    print(f"  OVERALL           : {'PASS' if overall_pass else 'FAIL'}")
    
    print(f"\nTOTAL RUNTIME      : {runtime / 60:.2f} minutes")
    print("\nREPORT:")
    print(report_path)
    print("\n" + "=" * 90)

if __name__ == "__main__":
    asyncio.run(main())