"""
40-Scenario Benchmark Runner

Generates synthetic AIS, produces oil observations via DriftEngine,
ingests into PostGIS, runs blind attribution, and evaluates results.

Usage:
    python -m scripts.benchmark.runner
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

# ── project imports ──────────────────────────────────────────────────
from app.core.database import AsyncSessionLocal
from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.attribution_engine import AttributionEngine
from app.services.scoring_engine import ScoringEngine
from app.repositories.ais_repository import AISRepository

from scripts.synthetic.scenario import SyntheticScenarioConfig
from scripts.synthetic.generate_synthetic_ais import generate_scenario_dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "raw" / "era5_wind_2019-07-event.nc"
CMEMS_PATH = PROJECT_ROOT / "data" / "ocean" / "raw" / "med_currents_2019-07-event.nc"
OUTPUT_DIR = PROJECT_ROOT / "data" / "ais" / "processed"


# =====================================================================
# SCENARIO DEFINITIONS
# =====================================================================

def _base_scenarios() -> list[dict]:
    """20 base scenarios with varied locations/times/seeds."""
    # Safe domain: lat 31.0-36.0, lon 30.5-35.5, time July 13-17 2019
    configs = [
        # idx, lat, lon, day, hour, seed
        (1,  33.50, 34.00, 15, 12, 101),   # canonical location
        (2,  32.50, 31.50, 14, 10, 102),
        (3,  34.00, 33.00, 16,  8, 103),
        (4,  33.00, 32.00, 15, 14, 104),
        (5,  34.50, 32.00, 14, 16, 105),
        (6,  33.00, 31.50, 16, 12, 106),
        (7,  34.20, 34.00, 13, 10, 107),
        (8,  32.50, 33.50, 17,  6, 108),
        (9,  33.80, 31.50, 14, 14, 109),
        (10, 34.50, 33.00, 15,  8, 110),
        (11, 32.80, 34.00, 16, 10, 111),
        (12, 34.20, 32.50, 13, 16, 112),
        (13, 32.20, 32.00, 15, 10, 113),
        (14, 33.20, 34.00, 14, 12, 114),
        (15, 34.50, 31.50, 16, 14, 115),
        (16, 32.50, 33.00, 17,  8, 116),
        (17, 34.00, 31.00, 13, 12, 117),
        (18, 33.50, 32.50, 15, 16, 118),
        (19, 34.00, 34.00, 14,  8, 119),
        (20, 32.50, 31.50, 16, 10, 120),
    ]
    scenarios = []
    for idx, lat, lon, day, hour, seed in configs:
        scenarios.append({
            "idx": idx,
            "lat": lat,
            "lon": lon,
            "day": day,
            "hour": hour,
            "seed": seed,
            "scenario_type": "base",
            "num_decoys": 6,
            "num_background": 100,
        })
    return scenarios


def _hard_scenarios() -> list[dict]:
    """20 hard scenarios with more/better decoys."""
    configs = [
        (21, 33.50, 34.00, 15, 12, 201),
        (22, 32.80, 31.80, 14, 11, 202),
        (23, 34.20, 33.50, 16,  9, 203),
        (24, 33.30, 32.30, 15, 15, 204),
        (25, 34.00, 32.00, 14, 13, 205),
        (26, 32.20, 31.50, 16, 11, 206),
        (27, 34.20, 34.00, 13, 11, 207),
        (28, 32.30, 33.50, 17,  7, 208),
        (29, 33.60, 31.80, 14, 15, 209),
        (30, 34.50, 33.20, 15,  9, 210),
        (31, 32.60, 34.00, 16, 11, 211),
        (32, 34.00, 32.80, 13, 15, 212),
        (33, 32.50, 32.20, 15, 11, 213),
        (34, 33.00, 34.00, 14, 13, 214),
        (35, 34.30, 31.80, 16, 13, 215),
        (36, 32.80, 33.20, 17,  9, 216),
        (37, 34.50, 31.50, 13, 13, 217),
        (38, 33.80, 32.80, 15, 15, 218),
        (39, 34.20, 34.00, 14,  9, 219),
        (40, 32.20, 32.00, 16, 11, 220),
    ]
    scenarios = []
    for idx, lat, lon, day, hour, seed in configs:
        scenarios.append({
            "idx": idx,
            "lat": lat,
            "lon": lon,
            "day": day,
            "hour": hour,
            "seed": seed,
            "scenario_type": "hard",
            "num_decoys": 10,
            "num_background": 120,
        })
    return scenarios


def build_scenario_config(
    spec: dict,
    weather_service: WeatherService,
) -> tuple[SyntheticScenarioConfig, dict]:
    """
    Build a SyntheticScenarioConfig from a spec dict.
    
    Uses DriftEngine to compute the actual observation location
    (NOT manually typed coordinates).
    """
    idx = spec["idx"]
    scenario_id = f"BM-{idx:03d}"
    prefix = f"SYNTH-S{idx:03d}-"
    source_vessel_id = f"{prefix}SRC"

    release_time = datetime(
        2019, 7, spec["day"], spec["hour"], 0, 0,
        tzinfo=timezone.utc,
    )

    drift_duration_hours = 6.0

    # Compute observation via actual DriftEngine
    drift_engine = DriftEngine(
        weather_service=weather_service,
        windage=0.03,
    )

    trajectory = drift_engine.forward_drift(
        start_latitude=spec["lat"],
        start_longitude=spec["lon"],
        start_time=release_time,
        duration_hours=drift_duration_hours,
        timestep_minutes=15,
    )

    if not trajectory.states:
        raise RuntimeError(
            f"DriftEngine returned empty trajectory for scenario {scenario_id} "
            f"at ({spec['lat']}, {spec['lon']}, {release_time})"
        )

    obs_state = trajectory.end
    obs_lat = obs_state.latitude
    obs_lon = obs_state.longitude
    obs_time = release_time + timedelta(hours=drift_duration_hours)

    # Bounds: 0.5 degree around source
    bounds_margin = 0.5
    config = SyntheticScenarioConfig(
        scenario_id=scenario_id,
        release_lat=spec["lat"],
        release_lon=spec["lon"],
        release_time=release_time,
        observation_lat=obs_lat,
        observation_lon=obs_lon,
        observation_time=obs_time,
        drift_duration_hours=drift_duration_hours,
        bounds_lat_min=spec["lat"] - bounds_margin,
        bounds_lat_max=spec["lat"] + bounds_margin,
        bounds_lon_min=spec["lon"] - bounds_margin,
        bounds_lon_max=spec["lon"] + bounds_margin,
        num_background_vessels=spec["num_background"],
        num_decoy_vessels=spec["num_decoys"],
        vessel_id_prefix=prefix,
        source_vessel_id=source_vessel_id,
        decoy_start_id=1,
        seed=spec["seed"],
    )

    observation = {
        "scenario_id": scenario_id,
        "synthetic": True,
        "observation": {
            "latitude": obs_lat,
            "longitude": obs_lon,
            "timestamp": obs_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }

    return config, observation


# =====================================================================
# INGESTION
# =====================================================================

async def clean_scenario(scenario_id: str) -> None:
    """Remove all synthetic data for one scenario from the database."""
    async with AsyncSessionLocal() as session:
        # Delete AIS positions first (FK constraint)
        result = await session.execute(
            text("""
                DELETE FROM ais_positions
                WHERE scenario_id = :sid AND is_synthetic = TRUE
            """),
            {"sid": scenario_id},
        )
        deleted_positions = result.rowcount

        # Delete vessels that have no remaining positions
        # (only synthetic ones from this scenario's prefix)
        await session.execute(
            text("""
                DELETE FROM vessels v
                WHERE NOT EXISTS (
                    SELECT 1 FROM ais_positions ap
                    WHERE ap.vessel_id = v.vessel_id
                )
                AND v.vessel_id LIKE :prefix
            """),
            {"prefix": f"SYNTH-S%"},
        )

        await session.commit()
        logger.info(
            "Cleaned scenario %s: %d positions deleted",
            scenario_id,
            deleted_positions,
        )


async def ingest_scenario(
    df: pd.DataFrame,
    scenario_id: str,
) -> dict:
    """Ingest a scenario DataFrame into PostGIS. Returns verification dict."""
    
    # Validate required columns
    required = {
        "vessel_id", "timestamp", "longitude", "latitude",
        "speed", "course", "heading", "is_synthetic", "scenario_id",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    # Validate all records are synthetic
    if not df["is_synthetic"].all():
        raise ValueError("Non-synthetic records in scenario data")

    # Validate scenario_id consistency
    if not (df["scenario_id"] == scenario_id).all():
        raise ValueError(f"Inconsistent scenario_id in data")

    # Parse timestamps
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    async with AsyncSessionLocal() as session:
        # Insert vessels (upsert)
        vessels = df[["vessel_id"]].drop_duplicates()
        vessel_type_map = {}
        if "vessel_type" in df.columns:
            for _, row in df[["vessel_id", "vessel_type"]].drop_duplicates("vessel_id").iterrows():
                vessel_type_map[row["vessel_id"]] = row.get("vessel_type", "Unknown")

        country_map = {}
        if "country" in df.columns:
            for _, row in df[["vessel_id", "country"]].drop_duplicates("vessel_id").iterrows():
                country_map[row["vessel_id"]] = row.get("country", "UN")

        for _, row in vessels.iterrows():
            vid = row["vessel_id"]
            await session.execute(
                text("""
                    INSERT INTO vessels (vessel_id, country, shiptype_name)
                    VALUES (:vid, :country, :stype)
                    ON CONFLICT (vessel_id) DO UPDATE SET
                        country = EXCLUDED.country,
                        shiptype_name = EXCLUDED.shiptype_name
                """),
                {
                    "vid": vid,
                    "country": country_map.get(vid, "UN"),
                    "stype": vessel_type_map.get(vid, "Unknown"),
                },
            )

        # Batch insert AIS positions
        batch_size = 500
        total = len(df)
        for start in range(0, total, batch_size):
            batch = df.iloc[start:start + batch_size]
            values_parts = []
            params = {}
            for i, (_, row) in enumerate(batch.iterrows()):
                key = f"_{start}_{i}"
                values_parts.append(
                    f"(:vid{key}, :ts{key}, :lon{key}, :lat{key}, "
                    f":spd{key}, :crs{key}, :hdg{key}, "
                    f"ST_SetSRID(ST_MakePoint(:lon{key}, :lat{key}), 4326), "
                    f"TRUE, :sid{key})"
                )
                params[f"vid{key}"] = row["vessel_id"]
                params[f"ts{key}"] = row["timestamp"].to_pydatetime()
                params[f"lon{key}"] = float(row["longitude"])
                params[f"lat{key}"] = float(row["latitude"])
                params[f"spd{key}"] = None if pd.isna(row["speed"]) else float(row["speed"])
                params[f"crs{key}"] = None if pd.isna(row["course"]) else float(row["course"])
                params[f"hdg{key}"] = None if pd.isna(row["heading"]) else float(row["heading"])
                params[f"sid{key}"] = scenario_id

            sql = f"""
                INSERT INTO ais_positions (
                    vessel_id, timestamp, longitude, latitude,
                    speed, course, heading, geometry,
                    is_synthetic, scenario_id
                ) VALUES {', '.join(values_parts)}
            """
            await session.execute(text(sql), params)

        await session.commit()

        # Verification
        result = await session.execute(
            text("SELECT COUNT(*) FROM ais_positions WHERE scenario_id = :sid"),
            {"sid": scenario_id},
        )
        row_count = result.scalar_one()

        result = await session.execute(
            text("SELECT COUNT(DISTINCT vessel_id) FROM ais_positions WHERE scenario_id = :sid"),
            {"sid": scenario_id},
        )
        vessel_count = result.scalar_one()

        return {
            "rows_inserted": row_count,
            "vessels_inserted": vessel_count,
        }


# =====================================================================
# ATTRIBUTION (BLIND)
# =====================================================================

async def run_attribution(
    weather_service: WeatherService,
    observation: dict,
    scenario_id: str,
) -> dict:
    """Run blind attribution. No ground truth access."""
    obs = observation["observation"]

    engine = AttributionEngine(
        weather_service=weather_service,
        ais_repository=AISRepository(),
        scoring_engine=ScoringEngine(),
    )

    obs_time = datetime.fromisoformat(
        obs["timestamp"].replace("Z", "+00:00")
    )

    async with AsyncSessionLocal() as session:
        t0 = time.perf_counter()
        result = await engine.attribute(
            db=session,
            observation_latitude=obs["latitude"],
            observation_longitude=obs["longitude"],
            observation_time=obs_time,
            drift_duration_hours=6.0,
            ensemble_size=100,
            initial_radius_m=500.0,
            timestep_minutes=15,
            candidate_radius_margin_km=5.0,
            candidate_time_window_hours=2.0,
            synthetic_only=True,
            scenario_id=scenario_id,
        )
        elapsed = time.perf_counter() - t0

    result["attribution_time_seconds"] = round(elapsed, 3)
    return result


# =====================================================================
# EVALUATION (POST-HOC)
# =====================================================================

def evaluate_scenario(
    prediction: dict,
    ground_truth: dict,
) -> dict:
    """Compare prediction with ground truth. Called ONLY after attribution."""
    
    true_vessel = ground_truth["source"]["vessel_id"]
    true_lat = ground_truth["source"]["latitude"]
    true_lon = ground_truth["source"]["longitude"]

    candidates = prediction.get("candidates", [])
    candidate_ids = [c["vessel_id"] for c in candidates]
    candidate_count = prediction.get("candidate_count", len(candidates))

    # Source estimate error
    src_est = prediction.get("source_estimate", {})
    est_lat = src_est.get("latitude", 0)
    est_lon = src_est.get("longitude", 0)

    source_error_km = _haversine_km(true_lat, true_lon, est_lat, est_lon)

    # Find rank of true vessel
    true_vessel_rank = None
    for i, c in enumerate(candidates):
        if c["vessel_id"] == true_vessel:
            true_vessel_rank = i + 1
            break

    candidate_recall = 1 if true_vessel in candidate_ids else 0
    top1_correct = 1 if true_vessel_rank == 1 else 0
    top3_correct = 1 if true_vessel_rank is not None and true_vessel_rank <= 3 else 0

    top_score = candidates[0]["score"] if candidates else 0.0
    second_score = candidates[1]["score"] if len(candidates) >= 2 else 0.0
    score_margin = top_score - second_score

    predicted_vessel = candidates[0]["vessel_id"] if candidates else None

    return {
        "true_source_vessel_id": true_vessel,
        "predicted_vessel_id": predicted_vessel,
        "true_vessel_rank": true_vessel_rank,
        "candidate_count": candidate_count,
        "candidate_recall": candidate_recall,
        "top1_correct": top1_correct,
        "top3_correct": top3_correct,
        "source_error_km": round(source_error_km, 4),
        "top_score": round(top_score, 4),
        "second_score": round(second_score, 4),
        "score_margin": round(score_margin, 4),
        "attribution_time_seconds": prediction.get("attribution_time_seconds", 0),
    }


def compute_summary(results: list[dict]) -> dict:
    """Compute aggregate benchmark metrics."""
    total = len(results)
    if total == 0:
        return {"total_scenarios": 0, "error": "No results"}

    successful = sum(1 for r in results if r.get("candidate_count", 0) > 0)
    recalls = [r["candidate_recall"] for r in results]
    top1s = [r["top1_correct"] for r in results]
    top3s = [r["top3_correct"] for r in results]
    errors = [r["source_error_km"] for r in results]
    counts = [r["candidate_count"] for r in results]
    margins = [r["score_margin"] for r in results]

    # MRR
    mrr_values = []
    for r in results:
        rank = r["true_vessel_rank"]
        if rank is not None:
            mrr_values.append(1.0 / rank)
        else:
            mrr_values.append(0.0)

    return {
        "total_scenarios": total,
        "successful_runs": successful,
        "candidate_recall": round(sum(recalls) / total, 4),
        "top1_accuracy": round(sum(top1s) / total, 4),
        "top3_accuracy": round(sum(top3s) / total, 4),
        "mrr": round(sum(mrr_values) / total, 4),
        "mean_source_error_km": round(float(np.mean(errors)), 4),
        "median_source_error_km": round(float(np.median(errors)), 4),
        "mean_candidate_count": round(float(np.mean(counts)), 2),
        "median_candidate_count": round(float(np.median(counts)), 2),
        "min_candidate_count": int(min(counts)),
        "max_candidate_count": int(max(counts)),
        "mean_score_margin": round(float(np.mean(margins)), 4),
    }


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# =====================================================================
# MAIN RUNNER
# =====================================================================

async def run_benchmark() -> None:
    """Execute the full 40-scenario benchmark."""

    logger.info("=" * 80)
    logger.info("OIL SPILL ATTRIBUTION BENCHMARK")
    logger.info("=" * 80)

    # ── Safety: check real AIS ────────────────────────────────────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM ais_positions WHERE is_synthetic = FALSE")
        )
        real_count = result.scalar_one()
        logger.info("Real AIS records: %d (PROTECTED)", real_count)
        assert real_count >= 10000, f"Expected >= 10000 real AIS, got {real_count}"

    # ── Open weather data ────────────────────────────────────────
    weather_service = WeatherService(
        era5_path=ERA5_PATH,
        cmems_path=CMEMS_PATH,
    )

    all_specs = _base_scenarios() + _hard_scenarios()
    all_results = []
    failed_scenarios = []

    for spec in all_specs:
        scenario_id = f"BM-{spec['idx']:03d}"
        scenario_type = spec["scenario_type"]
        logger.info("-" * 60)
        logger.info("SCENARIO %s (%s)", scenario_id, scenario_type)

        try:
            # 1. Build config + compute observation via DriftEngine
            config, observation = build_scenario_config(spec, weather_service)

            # 2. Generate synthetic AIS
            df, ground_truth = generate_scenario_dataset(config)

            # Add observation info to ground_truth
            ground_truth["observation"]["latitude"] = config.observation_lat
            ground_truth["observation"]["longitude"] = config.observation_lon
            ground_truth["observation"]["timestamp"] = config.observation_time.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

            # 3. Save artifacts
            csv_path = OUTPUT_DIR / f"{scenario_id}.csv"
            gt_path = OUTPUT_DIR / f"{scenario_id}_gt.json"
            obs_path = OUTPUT_DIR / f"{scenario_id}_obs.json"

            df.to_csv(csv_path, index=False)
            with open(gt_path, "w") as f:
                json.dump(ground_truth, f, indent=2)
            with open(obs_path, "w") as f:
                json.dump(observation, f, indent=2)

            logger.info(
                "Generated: %d records, %d vessels",
                len(df), df["vessel_id"].nunique(),
            )

            # 4. Clean old data for this scenario
            await clean_scenario(scenario_id)

            # 5. Ingest into PostGIS
            verification = await ingest_scenario(df, scenario_id)
            logger.info(
                "Ingested: %d rows, %d vessels",
                verification["rows_inserted"],
                verification["vessels_inserted"],
            )

            # 6. Run BLIND attribution (observation only, no ground truth)
            prediction = await run_attribution(
                weather_service, observation, scenario_id,
            )
            logger.info(
                "Attribution: %d candidates, top=%s, time=%.3fs",
                prediction.get("candidate_count", 0),
                prediction.get("top_prediction", "NONE"),
                prediction.get("attribution_time_seconds", 0),
            )

            # 7. POST-HOC evaluation (ground truth loaded only here)
            eval_result = evaluate_scenario(prediction, ground_truth)
            eval_result["scenario_id"] = scenario_id
            eval_result["scenario_type"] = scenario_type

            all_results.append(eval_result)

            status_str = (
                "✓ TOP-1" if eval_result["top1_correct"]
                else f"✗ rank={eval_result['true_vessel_rank']}"
            )
            logger.info(
                "Result: %s | recall=%d | error=%.2fkm | margin=%.4f",
                status_str,
                eval_result["candidate_recall"],
                eval_result["source_error_km"],
                eval_result["score_margin"],
            )

        except Exception as e:
            logger.error("FAILED scenario %s: %s", scenario_id, e, exc_info=True)
            failed_scenarios.append({
                "scenario_id": scenario_id,
                "error": str(e),
            })
            all_results.append({
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "true_source_vessel_id": "ERROR",
                "predicted_vessel_id": None,
                "true_vessel_rank": None,
                "candidate_count": 0,
                "candidate_recall": 0,
                "top1_correct": 0,
                "top3_correct": 0,
                "source_error_km": 999.0,
                "top_score": 0.0,
                "second_score": 0.0,
                "score_margin": 0.0,
                "attribution_time_seconds": 0.0,
            })

    weather_service.close()

    # ── Write results ────────────────────────────────────────────
    results_csv = OUTPUT_DIR / "benchmark_results.csv"
    fieldnames = [
        "scenario_id", "scenario_type", "true_source_vessel_id",
        "predicted_vessel_id", "true_vessel_rank", "candidate_count",
        "candidate_recall", "top1_correct", "top3_correct",
        "source_error_km", "top_score", "second_score", "score_margin",
        "attribution_time_seconds",
    ]

    with open(results_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_results:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    logger.info("Results written to %s", results_csv)

    # ── Summary ──────────────────────────────────────────────────
    summary = compute_summary(all_results)

    # Also compute base/hard separately
    base_results = [r for r in all_results if r.get("scenario_type") == "base"]
    hard_results = [r for r in all_results if r.get("scenario_type") == "hard"]

    summary["base_scenarios"] = compute_summary(base_results) if base_results else {}
    summary["hard_scenarios"] = compute_summary(hard_results) if hard_results else {}

    if failed_scenarios:
        summary["failed_scenarios"] = failed_scenarios

    summary_path = OUTPUT_DIR / "benchmark_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("Summary written to %s", summary_path)

    # ── Final report ─────────────────────────────────────────────
    logger.info("=" * 80)
    logger.info("BENCHMARK COMPLETE")
    logger.info("=" * 80)
    logger.info("Total scenarios:     %d", summary["total_scenarios"])
    logger.info("Successful runs:     %d", summary["successful_runs"])
    logger.info("Candidate recall:    %.2f%%", summary["candidate_recall"] * 100)
    logger.info("Top-1 accuracy:      %.2f%%", summary["top1_accuracy"] * 100)
    logger.info("Top-3 accuracy:      %.2f%%", summary["top3_accuracy"] * 100)
    logger.info("MRR:                 %.4f", summary["mrr"])
    logger.info("Mean source error:   %.4f km", summary["mean_source_error_km"])
    logger.info("Median source error: %.4f km", summary["median_source_error_km"])
    logger.info("Mean candidates:     %.2f", summary["mean_candidate_count"])
    logger.info("Mean score margin:   %.4f", summary["mean_score_margin"])

    if failed_scenarios:
        logger.warning("FAILED SCENARIOS: %d", len(failed_scenarios))
        for f in failed_scenarios:
            logger.warning("  %s: %s", f["scenario_id"], f["error"])

    # Verify real AIS not affected
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM ais_positions WHERE is_synthetic = FALSE")
        )
        final_real = result.scalar_one()
        logger.info("Real AIS after benchmark: %d (was %d)", final_real, real_count)
        assert final_real == real_count, "REAL AIS RECORDS WERE MODIFIED!"


if __name__ == "__main__":
    asyncio.run(run_benchmark())
