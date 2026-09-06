#!/usr/bin/env python3
import glob
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def parse_spill_file(filepath: str):
    """Parses a JSON file which may contain a list of detections or a single detection."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "detections" in data:
        raw_list = data["detections"]
    elif isinstance(data, list):
        raw_list = data
    else:
        raw_list = [data]

    parsed_records = []

    for item in raw_list:
        spill_id = item.get("spill_id") or Path(filepath).stem

        ts_raw = (
            item.get("detected_at")
            or item.get("timestamp")
            or item.get("detection_time")
            or item.get("acquisition_time")
        )
        obs_time = None
        if ts_raw:
            try:
                ts_clean = ts_raw.replace("Z", "+00:00")
                obs_time = datetime.fromisoformat(ts_clean)
                if obs_time.tzinfo is None:
                    obs_time = obs_time.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        lat, lon = None, None
        if "centroid" in item and isinstance(item["centroid"], dict):
            lat = item["centroid"].get("lat")
            lon = item["centroid"].get("lon")

        if lat is None or lon is None:
            lat = item.get("lat") or item.get("latitude")
            lon = item.get("lon") or item.get("longitude")

        if (lat is None or lon is None) and "polygon" in item and item["polygon"]:
            coords = item["polygon"]
            lon = sum(pt[0] for pt in coords) / len(coords)
            lat = sum(pt[1] for pt in coords) / len(coords)

        age_hours = float(
            item.get("estimated_age_hours")
            or item.get("spill_age_hours")
            or item.get("age_hours")
            or 12.0
        )

        parsed_records.append({
            "spill_id": spill_id,
            "filepath": filepath,
            "obs_time": obs_time,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "age_hours": age_hours,
        })

    return parsed_records


def run_audit():
    # Note: scanning json_output/coast and json_output/water
    patterns = [
        os.path.join("json_output", "coast", "*.json"),
        os.path.join("json_output", "water", "*.json"),
    ]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat))

    print(f"Discovered {len(files)} JSON files across coast and water directories.")
    if not files:
        print("No files found. Ensure you are running from the project root directory.")
        return

    all_detections = []
    missing_time = 0
    missing_coords = 0

    for fpath in files:
        records = parse_spill_file(fpath)
        for r in records:
            if not r["obs_time"]:
                missing_time += 1
            if r["lat"] is None or r["lon"] is None:
                missing_coords += 1
            all_detections.append(r)

    valid = [d for d in all_detections if d["obs_time"] and d["lat"] is not None and d["lon"] is not None]

    times = [d["obs_time"] for d in valid]
    lats = [d["lat"] for d in valid]
    lons = [d["lon"] for d in valid]

    min_time = min(times) if times else None
    max_time = max(times) if times else None
    min_lat, max_lat = (min(lats), max(lats)) if lats else (None, None)
    min_lon, max_lon = (min(lons), max(lons)) if lons else (None, None)

    # 2019 AIS window boundary
    ais_start = datetime.fromisoformat("2019-01-01T00:00:00+00:00")
    ais_end = datetime.fromisoformat("2020-01-01T12:00:00+00:00")

    in_2019 = sum(1 for t in times if ais_start <= t <= ais_end)

    print("\n--- DATASET AUDIT SUMMARY ---")
    print(f"Total JSON files scanned:       {len(files)}")
    print(f"Total detections extracted:     {len(all_detections)}")
    print(f"Successfully parsed detections: {len(valid)}")
    print(f"Missing/invalid timestamp:      {missing_time}")
    print(f"Missing/invalid coordinates:    {missing_coords}")
    if valid:
        print(f"Detection Date Range:           {min_time.isoformat()} to {max_time.isoformat()}")
        print(f"Latitude Bounding Box:          {min_lat:.4f}° to {max_lat:.4f}°")
        print(f"Longitude Bounding Box:         {min_lon:.4f}° to {max_lon:.4f}°")
        pct_2019 = (in_2019 / len(valid)) * 100
        print(f"Detections inside 2019 AIS era: {in_2019} / {len(valid)} ({pct_2019:.1f}%)")


if __name__ == "__main__":
    run_audit()