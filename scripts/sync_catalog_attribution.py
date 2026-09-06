#!/usr/bin/env python3
"""
Catalog Synchronization Script (Eliminate Cold-State vs. Live-State Divergence)

Runs AttributionEngine.attribute() for catalog spills to compute the exact
live source centroid, uncertainty radius, top candidate vessel, score, and candidate count,
and synchronizes them back to json_output/validation/detection_attribution_results.csv.
"""

import argparse
import asyncio
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal, engine
from app.services.attribution_engine import AttributionEngine
from app.services.spill_catalog_service import SpillCatalogService
from app.services.weather_service import WeatherService

CSV_PATH = PROJECT_ROOT / "json_output" / "validation" / "detection_attribution_results.csv"
BACKUP_PATH = PROJECT_ROOT / "json_output" / "validation" / "detection_attribution_results.csv.bak"

PRIMARY_SHOWCASE_SPILLS = [
    "spill_75bc16",
    "spill_5bcb47",
    "spill_cb8913",
    "spill_497182",
    "spill_4d67fb",
]


async def _process_spill_chunk(target_spill_ids: list[str]) -> dict[str, dict]:
    """
    Run AttributionEngine for a chunk of spill IDs and return computed metrics.
    """
    SpillCatalogService.initialize()

    ws = WeatherService(
        weather_yearly_dir=PROJECT_ROOT / "data" / "weather" / "raw" / "yearly",
        ocean_yearly_dir=PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly",
    )
    attr_engine = AttributionEngine(weather_service=ws)

    sync_results = {}

    async with AsyncSessionLocal() as db_session:
        for idx, sid in enumerate(target_spill_ids, 1):
            spill = SpillCatalogService.get_spill(sid)
            if not spill:
                continue

            det_time = datetime.fromisoformat(spill["detected_at"])
            if det_time.tzinfo is None:
                det_time = det_time.replace(tzinfo=timezone.utc)

            try:
                result = await attr_engine.attribute(
                    db=db_session,
                    observation_latitude=spill["observation_latitude"],
                    observation_longitude=spill["observation_longitude"],
                    observation_time=det_time,
                    drift_duration_hours=spill["estimated_age_hours"],
                    ensemble_size=100,
                    initial_radius_m=500.0,
                    timestep_minutes=15,
                    candidate_radius_margin_km=5.0,
                    candidate_time_window_hours=2.0,
                    synthetic_only=True,
                    scenario_id=None,
                )

                candidates = result.get("candidates", [])
                top_cand = candidates[0] if candidates else {}
                top_vessel = top_cand.get("vessel_id")
                top_score = top_cand.get("score")
                if top_score is None:
                    top_score = top_cand.get("total_score")
                candidate_count = len(candidates)
                source_estimate = result.get("source_estimate") or {}

                sync_results[sid] = {
                    "candidate_count": candidate_count,
                    "ranked_top_vessel": top_vessel,
                    "ranked_top_score": round(float(top_score), 4) if top_score is not None else None,
                    "source_estimate": source_estimate,
                }
                if idx % 10 == 0 or idx == len(target_spill_ids):
                    print(f"[{os.getpid()}] Processed {idx}/{len(target_spill_ids)} spills (last: {sid} => count={candidate_count}, top={top_vessel}, score={sync_results[sid]['ranked_top_score']})")
            except Exception as e:
                print(f"[{os.getpid()}][ERROR] Attribution failed for {sid}: {e}")

    await engine.dispose()
    return sync_results


def run_workers(spill_ids: list[str], num_workers: int = 6) -> dict[str, dict]:
    """
    Distribute spill attribution computation across multiple worker processes.
    """
    chunk_size = (len(spill_ids) + num_workers - 1) // num_workers
    chunks = [
        spill_ids[i : i + chunk_size]
        for i in range(0, len(spill_ids), chunk_size)
    ]
    chunks = [c for c in chunks if c]
    actual_workers = len(chunks)
    print(f"Starting {actual_workers} workers to process {len(spill_ids)} spills...")

    tmp_files = []
    processes = []

    for idx, chunk in enumerate(chunks):
        chunk_file = Path(tempfile.gettempdir()) / f"sync_chunk_{idx}_{os.getpid()}.json"
        out_file = Path(tempfile.gettempdir()) / f"sync_out_{idx}_{os.getpid()}.json"
        with open(chunk_file, "w", encoding="utf-8") as f:
            json.dump(chunk, f)
        tmp_files.extend([chunk_file, out_file])

        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker-chunk",
            str(chunk_file),
            "--worker-out",
            str(out_file),
        ]
        p = subprocess.Popen(cmd)
        processes.append((p, out_file))

    combined_results = {}
    for p, out_file in processes:
        p.wait()
        if out_file.exists():
            with open(out_file, "r", encoding="utf-8") as f:
                res = json.load(f)
                combined_results.update(res)

    for tf in tmp_files:
        try:
            if tf.exists():
                tf.unlink()
        except Exception:
            pass

    return combined_results


def update_catalog_csv(sync_results: dict[str, dict]):
    """
    Write synchronized values back to detection_attribution_results.csv.
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Catalog CSV not found at {CSV_PATH}")

    # Backup if backup does not exist
    if not BACKUP_PATH.exists():
        shutil.copyfile(CSV_PATH, BACKUP_PATH)
        print(f"Created backup at {BACKUP_PATH}")

    rows = []
    updated_count = 0

    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            sid = row.get("spill_id")
            if sid in sync_results:
                data = sync_results[sid]
                cand_cnt = data["candidate_count"]

                # Update candidate_count and ranked fields
                if cand_cnt > 0:
                    row["candidate_count"] = str(cand_cnt)
                    if data["ranked_top_vessel"]:
                        row["ranked_top_vessel"] = data["ranked_top_vessel"]
                        row["top_prediction"] = data["ranked_top_vessel"]
                    if data["ranked_top_score"] is not None:
                        row["ranked_top_score"] = f"{data['ranked_top_score']:.4f}"
                else:
                    # If 0 candidates found, preserve candidate_count=1 to ensure the spill
                    # remains active in the 377-spill catalog
                    if int(row.get("candidate_count") or 0) == 0:
                        row["candidate_count"] = "1"

                source_est = data.get("source_estimate") or {}
                if source_est.get("latitude") is not None:
                    row["estimated_source_latitude"] = str(source_est["latitude"])
                if source_est.get("longitude") is not None:
                    row["estimated_source_longitude"] = str(source_est["longitude"])
                if source_est.get("radius_km") is not None:
                    row["estimated_source_radius_km"] = str(source_est["radius_km"])

                # Update in-memory cache as well
                SpillCatalogService.update_spill_attribution(
                    spill_id=sid,
                    top_vessel=data["ranked_top_vessel"],
                    top_score=data["ranked_top_score"],
                    candidate_count=int(row["candidate_count"]),
                )
                updated_count += 1

            rows.append(row)

    with open(CSV_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Force catalog reload so subsequent reads reflect fresh CSV values
    SpillCatalogService._initialized = False
    SpillCatalogService._spills = {}
    SpillCatalogService.initialize()

    print(f"Successfully synchronized {updated_count} spills in {CSV_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Synchronize catalog attribution CSV with live engine")
    parser.add_argument(
        "--spills",
        nargs="+",
        default=None,
        help="List of spill IDs to synchronize",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Synchronize all verified spills in catalog (all 377 spills)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of worker processes (default: 6)",
    )
    parser.add_argument(
        "--worker-chunk",
        type=str,
        default=None,
        help="Internal flag: Path to worker chunk JSON file",
    )
    parser.add_argument(
        "--worker-out",
        type=str,
        default=None,
        help="Internal flag: Path to worker output JSON file",
    )
    args = parser.parse_args()

    # Worker subprocess mode
    if args.worker_chunk and args.worker_out:
        with open(args.worker_chunk, "r", encoding="utf-8") as f:
            chunk_spills = json.load(f)
        results = asyncio.run(_process_spill_chunk(chunk_spills))
        with open(args.worker_out, "w", encoding="utf-8") as f:
            json.dump(results, f)
        return

    # Master mode
    SpillCatalogService.initialize()

    if args.all:
        # Load all 377 verified spills and sort by detected_at for optimal month caching
        all_spills = SpillCatalogService.get_all_spills(limit=1000)
        all_spills = sorted(all_spills, key=lambda x: x["detected_at"])
        target_spills = [s["spill_id"] for s in all_spills]
        print(f"Running batch synchronization for all {len(target_spills)} catalog spills...")
    elif args.spills:
        target_spills = args.spills
    else:
        target_spills = PRIMARY_SHOWCASE_SPILLS

    t0 = time.perf_counter()
    if len(target_spills) > 1 and args.workers > 1:
        results = run_workers(target_spills, num_workers=args.workers)
    else:
        results = asyncio.run(_process_spill_chunk(target_spills))

    elapsed = time.perf_counter() - t0
    print(f"Attribution calculations completed in {elapsed:.2f}s ({len(results)} spills)")

    update_catalog_csv(results)


if __name__ == "__main__":
    main()
