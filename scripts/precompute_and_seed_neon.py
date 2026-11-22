import os
import sys
import time
import math
import json
import socket
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Set, Tuple

import pandas as pd
import numpy as np
from dotenv import load_dotenv
import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Setup DNS workaround for Neon on local machines if necessary
orig_getaddrinfo = socket.getaddrinfo
def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if 'neon.tech' in host:
        return orig_getaddrinfo('3.147.219.177', port, family, type, proto, flags)
    return orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = custom_getaddrinfo

from app.services.spill_catalog_service import SpillCatalogService
from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine
from app.services.hindcast_service import HindcastService
from app.services.visualization_service import VisualizationService
from app.services.demo_vessel_evidence_service import DemoVesselEvidenceService
from app.routers.demo_spills import _build_spill_vessels, _infer_shiptype_code
from app.models.schemas import (
    DemoSpillDetail,
    CentroidSchema,
    DemoBacktrackResponse,
    SpillPredictionResponse,
    PredictedPosition,
    PredictionTrajectoryPoint,
    DemoAttributionTrajectoryResponse,
    DemoSpillVesselResponse,
)

PRECOMPUTED_DIR = PROJECT_ROOT / "data" / "precomputed"
AIS_CACHE_FILE = PROJECT_ROOT / "data" / "precomputed_ais.json"
PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)

class SimpleAISPosition:
    def __init__(self, timestamp: datetime, latitude: float, longitude: float, speed: float = None, course: float = None, heading: float = None):
        self.timestamp = timestamp
        self.latitude = latitude
        self.longitude = longitude
        self.speed = speed
        self.course = course
        self.heading = heading

class SimpleVessel:
    def __init__(self, vessel_id: str, country: str = "GR", shiptype: int = 70, shiptype_name: str = "Cargo"):
        self.vessel_id = vessel_id
        self.country = country
        self.shiptype = shiptype
        self.shiptype_name = shiptype_name


def get_or_create_ais_data(spills: List[Dict[str, Any]]):
    """
    Extract or load cached downsampled (5-min) AIS pings for all target vessels.
    """
    if AIS_CACHE_FILE.exists():
        print(f"Loading cached AIS data from {AIS_CACHE_FILE}...")
        with open(AIS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        vessels_dict = {
            v["vessel_id"]: SimpleVessel(v["vessel_id"], v["country"], v["shiptype"], v["shiptype_name"])
            for v in data["vessels"]
        }
        positions_by_vessel = {}
        for p in data["positions"]:
            vid = p["vessel_id"]
            ts = datetime.fromisoformat(p["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            pos_obj = SimpleAISPosition(ts, p["latitude"], p["longitude"], p.get("speed"), p.get("course"), p.get("heading"))
            if vid not in positions_by_vessel:
                positions_by_vessel[vid] = []
            positions_by_vessel[vid].append(pos_obj)
        print(f"Loaded {len(vessels_dict)} vessels and {len(data['positions'])} AIS pings from disk cache.")
        return vessels_dict, positions_by_vessel, data["positions"]

    print("\n--- [Phase 1] Extracting & Downsampling AIS Pings from Yearly CSVs ---")
    month_vessel_windows: Dict[str, Dict[str, List[Tuple[datetime, datetime]]]] = {}
    
    for s in spills:
        v = s.get("ranked_top_vessel")
        if not v:
            continue
        rel = datetime.fromisoformat(s["estimated_release_time"])
        if rel.tzinfo is None:
            rel = rel.replace(tzinfo=timezone.utc)
        det = datetime.fromisoformat(s["detected_at"])
        if det.tzinfo is None:
            det = det.replace(tzinfo=timezone.utc)
        m = s["detected_at"][:7]
        t_start = rel - timedelta(hours=4)
        t_end = det + timedelta(hours=4)
        
        if m not in month_vessel_windows:
            month_vessel_windows[m] = {}
        if v not in month_vessel_windows[m]:
            month_vessel_windows[m][v] = []
        month_vessel_windows[m][v].append((t_start, t_end))
        
    vessels_dict: Dict[str, SimpleVessel] = {}
    positions_by_vessel: Dict[str, List[SimpleAISPosition]] = {}
    cached_positions_list: List[dict] = []
    seen_downsampled_keys: Set[Tuple[str, str]] = set()

    yearly_dir = PROJECT_ROOT / "data" / "ais" / "processed" / "yearly"

    for month_str, vdict in month_vessel_windows.items():
        csv_file = yearly_dir / f"synthetic_ais_{month_str}.csv"
        if not csv_file.exists():
            print(f"Warning: {csv_file} does not exist, skipping.")
            continue
            
        print(f"Scanning {csv_file.name} for {len(vdict)} target vessels...")
        target_vessels = set(vdict.keys())
        t0 = time.time()
        
        for chunk in pd.read_csv(csv_file, chunksize=150_000):
            matched = chunk[chunk["vessel_id"].isin(target_vessels)]
            if matched.empty:
                continue
                
            for _, row in matched.iterrows():
                vid = str(row["vessel_id"])
                ts_raw = row["timestamp"]
                ts = datetime.fromisoformat(str(ts_raw))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                    
                # Downsample to 5-minute intervals (:00, :05, :10, :15, ...)
                if ts.minute % 5 != 0 or ts.second != 0:
                    continue
                    
                # Check if timestamp is in any window for this vessel
                in_window = False
                for (w_start, w_end) in vdict[vid]:
                    if w_start <= ts <= w_end:
                        in_window = True
                        break
                if not in_window:
                    continue
                    
                if vid not in vessels_dict:
                    ctype = str(row.get("country") or "GR")
                    stname = str(row.get("vessel_type") or "Cargo")
                    code = _infer_shiptype_code(stname) or 70
                    vessels_dict[vid] = SimpleVessel(vid, ctype, code, stname)
                    
                pos_key = (vid, ts.isoformat())
                if pos_key in seen_downsampled_keys:
                    continue
                seen_downsampled_keys.add(pos_key)
                
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                spd = float(row["speed"]) if pd.notna(row.get("speed")) else None
                course = float(row["course"]) if pd.notna(row.get("course")) else None
                hdg = float(row["heading"]) if pd.notna(row.get("heading")) else None
                scenario = str(row.get("scenario_id") or "synthetic-2019")
                
                pos_obj = SimpleAISPosition(ts, lat, lon, spd, course, hdg)
                if vid not in positions_by_vessel:
                    positions_by_vessel[vid] = []
                positions_by_vessel[vid].append(pos_obj)
                
                cached_positions_list.append({
                    "vessel_id": vid,
                    "timestamp": ts.isoformat(),
                    "longitude": lon,
                    "latitude": lat,
                    "speed": spd,
                    "course": course,
                    "heading": hdg,
                    "is_synthetic": True,
                    "scenario_id": scenario
                })
                
        print(f"  Finished {month_str} in {time.time()-t0:.1f}s.")

    for vid in positions_by_vessel:
        positions_by_vessel[vid].sort(key=lambda p: p.timestamp)
        
    print(f"Extracted {len(vessels_dict)} unique vessels and {len(cached_positions_list)} downsampled (5-min) AIS pings.")
    
    # Save cache to disk
    with open(AIS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "vessels": [
                {"vessel_id": v.vessel_id, "country": v.country, "shiptype": v.shiptype, "shiptype_name": v.shiptype_name}
                for v in vessels_dict.values()
            ],
            "positions": cached_positions_list
        }, f)
    print(f"Saved AIS cache to {AIS_CACHE_FILE}.")
    return vessels_dict, positions_by_vessel, cached_positions_list


async def precompute_spills():
    SpillCatalogService.initialize()
    total_spills = SpillCatalogService.get_total_count()
    all_spills = SpillCatalogService.get_all_spills(0, total_spills)
    print(f"Loaded {len(all_spills)} demo spills from catalog.")

    vessels_dict, positions_by_vessel, ais_list = get_or_create_ais_data(all_spills)

    # Diagnostic URLs
    diag_urls_path = PROJECT_ROOT / "json_output" / "validation" / "diagnostic_plot_urls.json"
    diag_urls = {}
    if diag_urls_path.exists():
        with open(diag_urls_path, "r", encoding="utf-8") as f:
            diag_urls = json.load(f)

    # Check which spills still need computation
    missing_spills = []
    for s in all_spills:
        sp_file = PRECOMPUTED_DIR / f"{s['spill_id']}.json"
        if not sp_file.exists():
            missing_spills.append(s)

    if not missing_spills:
        print(f"All {len(all_spills)} spills already precomputed in {PRECOMPUTED_DIR}!")
    else:
        print(f"\n--- [Phase 2] Precomputing Physics for {len(missing_spills)} Remaining Spills ---")
        ws = WeatherService(
            weather_yearly_dir=PROJECT_ROOT / "data" / "weather" / "raw" / "yearly",
            ocean_yearly_dir=PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly",
        )
        de = DriftEngine(weather_service=ws, windage=0.03)
        hs = HindcastService(drift_engine=de)
        vs = VisualizationService(drift_engine=de, hindcast_service=hs)
        evidence_service = DemoVesselEvidenceService()

        t0 = time.time()
        for idx, s in enumerate(missing_spills, 1):
            spill_id = s["spill_id"]
            start_lat = float(s["observation_latitude"])
            start_lon = float(s["observation_longitude"])
            detected_at = datetime.fromisoformat(s["detected_at"])
            if detected_at.tzinfo is None:
                detected_at = detected_at.replace(tzinfo=timezone.utc)
            detected_at_naive = detected_at.replace(tzinfo=None)

            # 1. Detail
            detail_obj = DemoSpillDetail(
                spill_id=spill_id,
                source_type=s["source_type"],
                source_file=s["source_file"],
                detected_at=detected_at,
                estimated_age_hours=s["estimated_age_hours"],
                estimated_release_time=datetime.fromisoformat(s["estimated_release_time"]),
                observation_latitude=start_lat,
                observation_longitude=start_lon,
                centroid=CentroidSchema(lon=start_lon, lat=start_lat),
                polygon=s["polygon"],
                area_km2=s["area_km2"],
                confidence_score=s["confidence_score"],
                image_url=s["image_reference"],
                estimated_source_latitude=s["estimated_source_latitude"],
                estimated_source_longitude=s["estimated_source_longitude"],
                estimated_source_radius_km=s["estimated_source_radius_km"],
                candidate_count=s["candidate_count"],
                ranked_top_vessel=s["ranked_top_vessel"],
                ranked_top_score=s["ranked_top_score"],
                runtime_seconds=s["runtime_seconds"],
            )

            # 2. Visualization
            viz = vs.get_spill_visualization(spill_id)

            # 3. Forecast
            drift_traj = de.forward_drift(
                start_latitude=start_lat,
                start_longitude=start_lon,
                start_time=detected_at_naive,
                duration_hours=6.0,
                timestep_minutes=15
            )
            states = drift_traj.states
            trajectory_points = []
            speed_records_knots = []
            for state in states:
                u = state.drift_u
                v = state.drift_v
                spd_mps = float(math.hypot(u, v))
                spd_knots = float(spd_mps * 1.94384)
                speed_records_knots.append(spd_knots)
                heading_deg = float((math.degrees(math.atan2(u, v)) + 360.0) % 360.0)
                dist_km = float(DriftEngine.haversine_km(start_lat, start_lon, state.latitude, state.longitude))
                trajectory_points.append(
                    PredictionTrajectoryPoint(
                        timestamp=state.timestamp,
                        latitude=round(float(state.latitude), 6),
                        longitude=round(float(state.longitude), 6),
                        drift_speed_knots=round(spd_knots, 2),
                        drift_heading_deg=round(heading_deg, 1),
                        distance_from_start_km=round(dist_km, 3),
                    )
                )
            final_state = states[-1]
            final_lat = float(final_state.latitude)
            final_lon = float(final_state.longitude)
            total_disp = float(DriftEngine.haversine_km(start_lat, start_lon, final_lat, final_lon))
            d_lon = math.radians(final_lon - start_lon)
            lat1_rad = math.radians(start_lat)
            lat2_rad = math.radians(final_lat)
            y = math.sin(d_lon) * math.cos(lat2_rad)
            x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
            net_bearing = float((math.degrees(math.atan2(y, x)) + 360.0) % 360.0)
            avg_speed = float(np.mean(speed_records_knots)) if speed_records_knots else 0.0

            forecast = SpillPredictionResponse(
                spill_id=spill_id,
                forecast_hours=6.0,
                initial_position=PredictedPosition(
                    latitude=round(start_lat, 6),
                    longitude=round(start_lon, 6),
                    timestamp=detected_at,
                ),
                predicted_position=PredictedPosition(
                    latitude=round(final_lat, 6),
                    longitude=round(final_lon, 6),
                    timestamp=final_state.timestamp,
                ),
                total_displacement_km=round(total_disp, 3),
                net_heading_deg=round(net_bearing, 1),
                average_speed_knots=round(avg_speed, 2),
                trajectory=trajectory_points,
            )

            # 4. Vessels and Attribution
            real_vessel_id = s.get("ranked_top_vessel")
            vessel_meta = vessels_dict.get(real_vessel_id) if real_vessel_id else None
            vessel_positions = positions_by_vessel.get(real_vessel_id, []) if real_vessel_id else []

            vessel_resp = await _build_spill_vessels(
                spill_id=spill_id,
                db=None,
                prefetched_vessel=vessel_meta,
                prefetched_positions=vessel_positions
            )
            evidence_resp = await evidence_service.build(
                db=None,
                spill=s,
                vessels=vessel_resp.vessels,
                prefetched_vessel=vessel_meta,
                prefetched_widest_positions=vessel_positions
            )
            attrib_validated = DemoAttributionTrajectoryResponse(**evidence_resp)

            # 5. Backtrack
            backtrack = DemoBacktrackResponse(
                spill_id=spill_id,
                backtrack={
                    "observation": {
                        "latitude": start_lat,
                        "longitude": start_lon,
                        "timestamp": s["detected_at"],
                    },
                    "estimated_release_time": s.get("estimated_release_time"),
                    "source_estimate": {
                        "latitude": s.get("estimated_source_latitude"),
                        "longitude": s.get("estimated_source_longitude"),
                        "radius_km": s.get("estimated_source_radius_km"),
                    },
                },
                attribution={
                    "candidate_count": s.get("candidate_count", 0),
                    "top_vessel": s.get("ranked_top_vessel"),
                    "top_score": s.get("ranked_top_score"),
                }
            )

            # Save to disk immediately
            spill_bundle = {
                "spill_id": spill_id,
                "detected_at": detected_at.isoformat(),
                "centroid_lat": start_lat,
                "centroid_lon": start_lon,
                "area_km2": float(s["area_km2"]),
                "confidence_score": float(s["confidence_score"]),
                "candidate_count": int(s["candidate_count"]),
                "ranked_top_vessel": s.get("ranked_top_vessel"),
                "ranked_top_score": float(s["ranked_top_score"]) if s.get("ranked_top_score") else None,
                "image_url": s.get("image_reference"),
                "polygon": s["polygon"],
                "detail_payload": detail_obj.model_dump(mode="json"),
                "visualization_payload": viz.model_dump(mode="json"),
                "forecast_payload": forecast.model_dump(mode="json"),
                "vessels_payload": vessel_resp.model_dump(mode="json"),
                "attribution_payload": attrib_validated.model_dump(mode="json"),
                "backtrack_payload": backtrack.model_dump(mode="json"),
                "diagnostic_plot_url": diag_urls.get(spill_id),
            }
            with open(PRECOMPUTED_DIR / f"{spill_id}.json", "w", encoding="utf-8") as f:
                json.dump(spill_bundle, f)

            if idx % 25 == 0 or idx == len(missing_spills):
                print(f"[{idx}/{len(missing_spills)}] Saved {spill_id} | Elapsed: {time.time()-t0:.1f}s")

        ws.close()
        print("All missing spills computed and persisted to disk!")


async def seed_neon():
    load_dotenv(PROJECT_ROOT / ".env")
    neon_url = os.getenv("NEON_URL")
    if not neon_url:
        raise ValueError("NEON_URL not found in .env")

    print("\n--- [Phase 3] Seeding Neon PostgreSQL from Local Disk Cache ---")
    
    # Load AIS cache
    with open(AIS_CACHE_FILE, "r", encoding="utf-8") as f:
        ais_cache = json.load(f)
    vessels = ais_cache["vessels"]
    positions = ais_cache["positions"]

    # Load all precomputed spills
    spill_files = list(PRECOMPUTED_DIR.glob("*.json"))
    print(f"Loaded {len(vessels)} vessels, {len(positions)} AIS positions, and {len(spill_files)} precomputed spills from disk.")

    conn = await asyncpg.connect(neon_url)

    # 1. Vessels
    print("Seeding vessels table...")
    v_tuples = [(v["vessel_id"], v["country"], v["shiptype"], v["shiptype_name"]) for v in vessels]
    await conn.executemany("""
        INSERT INTO vessels (vessel_id, country, shiptype, shiptype_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (vessel_id) DO UPDATE SET country=EXCLUDED.country, shiptype=EXCLUDED.shiptype, shiptype_name=EXCLUDED.shiptype_name;
    """, v_tuples)

    # 2. AIS positions in batches of 2000
    print(f"Seeding {len(positions)} downsampled AIS positions...")
    await conn.execute("TRUNCATE TABLE ais_positions;")
    batch_size = 2000
    for i in range(0, len(positions), batch_size):
        batch = positions[i:i+batch_size]
        p_tuples = [
            (
                p["vessel_id"],
                datetime.fromisoformat(p["timestamp"]),
                p["longitude"],
                p["latitude"],
                p["speed"],
                p["course"],
                p["heading"],
                p["is_synthetic"],
                p["scenario_id"]
            )
            for p in batch
        ]
        await conn.executemany("""
            INSERT INTO ais_positions (vessel_id, timestamp, longitude, latitude, speed, course, heading, geometry, is_synthetic, scenario_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, ST_SetSRID(ST_MakePoint($3, $4), 4326), $8, $9);
        """, p_tuples)

    # 3. Spills data
    print(f"Seeding {len(spill_files)} spills across catalog and payload tables...")
    await conn.execute("TRUNCATE TABLE spills_catalog CASCADE;")

    cat_rows = []
    viz_rows = []
    fc_rows = []
    vess_rows = []
    attr_rows = []
    bt_rows = []
    dp_rows = []

    for sp_file in spill_files:
        with open(sp_file, "r", encoding="utf-8") as f:
            b = json.load(f)
        spill_id = b["spill_id"]
        cat_rows.append((
            spill_id,
            datetime.fromisoformat(b["detected_at"]),
            b["centroid_lat"],
            b["centroid_lon"],
            b["area_km2"],
            b["confidence_score"],
            b["candidate_count"],
            b.get("ranked_top_vessel"),
            b.get("ranked_top_score"),
            b.get("image_url"),
            json.dumps(b["polygon"]),
            json.dumps(b["detail_payload"])
        ))
        viz_rows.append((spill_id, json.dumps(b["visualization_payload"])))
        fc_rows.append((spill_id, json.dumps(b["forecast_payload"])))
        vess_rows.append((spill_id, json.dumps(b["vessels_payload"])))
        attr_rows.append((spill_id, json.dumps(b["attribution_payload"])))
        bt_rows.append((spill_id, json.dumps(b["backtrack_payload"])))
        if b.get("diagnostic_plot_url"):
            dp_rows.append((spill_id, b["diagnostic_plot_url"]))

    await conn.executemany("""
        INSERT INTO spills_catalog (spill_id, detected_at, centroid_lat, centroid_lon, area_km2, confidence_score, candidate_count, ranked_top_vessel, ranked_top_score, image_url, polygon, detail_payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb);
    """, cat_rows)

    await conn.executemany("""
        INSERT INTO spill_visualizations (spill_id, payload)
        VALUES ($1, $2::jsonb);
    """, viz_rows)

    await conn.executemany("""
        INSERT INTO spill_forecasts (spill_id, payload)
        VALUES ($1, $2::jsonb);
    """, fc_rows)

    await conn.executemany("""
        INSERT INTO spill_vessels (spill_id, payload)
        VALUES ($1, $2::jsonb);
    """, vess_rows)

    await conn.executemany("""
        INSERT INTO spill_attributions (spill_id, payload)
        VALUES ($1, $2::jsonb);
    """, attr_rows)

    await conn.executemany("""
        INSERT INTO spill_backtracks (spill_id, payload)
        VALUES ($1, $2::jsonb);
    """, bt_rows)

    await conn.executemany("""
        INSERT INTO diagnostic_plots (spill_id, plot_url)
        VALUES ($1, $2)
        ON CONFLICT (spill_id) DO UPDATE SET plot_url=EXCLUDED.plot_url;
    """, dp_rows)

    print("\n--- [Phase 4] Verification Counts in Neon ---")
    print("spills_catalog:      ", await conn.fetchval("SELECT count(*) FROM spills_catalog;"))
    print("spill_visualizations:", await conn.fetchval("SELECT count(*) FROM spill_visualizations;"))
    print("spill_forecasts:     ", await conn.fetchval("SELECT count(*) FROM spill_forecasts;"))
    print("spill_vessels:       ", await conn.fetchval("SELECT count(*) FROM spill_vessels;"))
    print("spill_attributions:  ", await conn.fetchval("SELECT count(*) FROM spill_attributions;"))
    print("spill_backtracks:    ", await conn.fetchval("SELECT count(*) FROM spill_backtracks;"))
    print("diagnostic_plots:    ", await conn.fetchval("SELECT count(*) FROM diagnostic_plots;"))
    print("vessels:             ", await conn.fetchval("SELECT count(*) FROM vessels;"))
    print("ais_positions:       ", await conn.fetchval("SELECT count(*) FROM ais_positions;"))

    await conn.close()
    print("\nSUCCESS! Neon database is completely seeded and verified.")


async def main():
    await precompute_spills()
    await seed_neon()

if __name__ == "__main__":
    asyncio.run(main())
