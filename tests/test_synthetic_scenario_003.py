import sys
import json
import math
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = PROJECT_ROOT / "data/ais/processed/synthetic_scenario_003.csv"
JSON_PATH = PROJECT_ROOT / "data/ais/processed/synthetic_scenario_003_ground_truth.json"
REPORT_PATH = PROJECT_ROOT / "reports/scenario_003_ais_validation_report.md"

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * r * math.asin(math.sqrt(a))

class ScenarioValidator:
    def __init__(self):
        self.df = None
        self.gt = None
        self.stats = {}
        self.passes = {}

    def load(self):
        if not CSV_PATH.exists() or not JSON_PATH.exists():
            return False

        self.df = pd.read_csv(CSV_PATH)
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])

        with open(JSON_PATH, "r") as f:
            self.gt = json.load(f)

        return True

    def validate_data_quality(self):
        req_cols = ["vessel_id", "timestamp", "longitude", "latitude", "speed", "course", "heading", "vessel_type", "country", "is_synthetic", "scenario_id"]

        has_cols = all(c in self.df.columns for c in req_cols)
        self.passes["Required columns"] = "PASS" if has_cols else "FAIL"

        valid_coords = self.df["latitude"].between(-90, 90).all() and self.df["longitude"].between(-180, 180).all() and not self.df[["latitude", "longitude"]].isna().any().any()
        self.passes["Valid coordinates"] = "PASS" if valid_coords else "FAIL"

        valid_timestamps = not self.df["timestamp"].isna().any()
        # check sorting
        is_sorted = True
        for vid, group in self.df.groupby("vessel_id"):
            if not group["timestamp"].is_monotonic_increasing:
                is_sorted = False
        self.passes["Valid timestamps"] = "PASS" if valid_timestamps and is_sorted else "FAIL"

        valid_speeds = (self.df["speed"] >= 0).all()
        self.passes["Valid speeds"] = "PASS" if valid_speeds else "FAIL"

        valid_course = self.df["course"].between(0, 360).all()
        self.passes["Valid courses"] = "PASS" if valid_course else "FAIL"

        valid_heading = self.df["heading"].between(0, 360).all()
        self.passes["Valid headings"] = "PASS" if valid_heading else "FAIL"

        scenario_ok = (self.df["scenario_id"] == "scenario-003").all()
        self.passes["Scenario ID"] = "PASS" if scenario_ok else "FAIL"

        synth_ok = (self.df["is_synthetic"] == True).all()
        self.passes["Synthetic flags"] = "PASS" if synth_ok else "FAIL"

    def validate_source(self):
        src_id = self.gt["source"]["vessel_id"]
        src_df = self.df[self.df["vessel_id"] == src_id].copy()
        if src_df.empty:
            for k in ["Approach", "Slowdown", "Release", "Loiter", "Departure"]:
                self.passes[k] = "FAIL"
            return

        rel_time = pd.to_datetime(self.gt["source"]["timestamp"])
        rel_lat = self.gt["source"]["latitude"]
        rel_lon = self.gt["source"]["longitude"]

        src_df["dist"] = src_df.apply(lambda row: haversine_km(row["latitude"], row["longitude"], rel_lat, rel_lon), axis=1)

        pre_release = src_df[src_df["timestamp"] < rel_time]
        post_release = src_df[src_df["timestamp"] > rel_time]

        # Approach
        if len(pre_release) > 5:
            dists = pre_release["dist"].values
            approach_decreasing = dists[0] > dists[-1]
            self.passes["Approach"] = "PASS" if approach_decreasing else "FAIL"
            self.stats["distance_start_to_source"] = dists[0]
            self.stats["speed_before_slowdown"] = pre_release.iloc[0]["speed"]
        else:
            self.passes["Approach"] = "FAIL"

        # Slowdown
        if len(pre_release) > 2:
            speed_early = pre_release.iloc[0]["speed"]
            speed_late = pre_release.iloc[-1]["speed"]
            self.passes["Slowdown"] = "PASS" if speed_late < speed_early else "FAIL"
            self.stats["speed_during_slowdown"] = speed_late
        else:
            self.passes["Slowdown"] = "FAIL"

        # Release
        exact = src_df[src_df["timestamp"] == rel_time]
        if not exact.empty:
            self.passes["Release"] = "PASS" if exact.iloc[0]["dist"] < 0.1 else "FAIL"
            self.stats["minimum_release_area_distance"] = exact.iloc[0]["dist"]
            self.stats["speed_at_release"] = exact.iloc[0]["speed"]
        else:
            self.passes["Release"] = "FAIL"

        # Loiter
        loiter_df = post_release[post_release["dist"] < 1.0]
        if not loiter_df.empty:
            loiter_dur = (loiter_df["timestamp"].max() - rel_time).total_seconds() / 60.0
            self.passes["Loiter"] = "PASS" if loiter_dur >= 10 else "FAIL"
            self.stats["loiter_duration"] = loiter_dur
        else:
            self.passes["Loiter"] = "FAIL"
            self.stats["loiter_duration"] = 0

        # Departure
        departure_df = post_release[post_release["dist"] >= 1.0]
        if not departure_df.empty:
            self.passes["Departure"] = "PASS" if departure_df.iloc[-1]["dist"] > 1.0 else "FAIL"
            self.stats["departure_speed"] = departure_df.iloc[-1]["speed"]
            self.stats["distance_traveled_after_departure"] = departure_df.iloc[-1]["dist"] - 1.0
        else:
            self.passes["Departure"] = "FAIL"
            self.stats["departure_speed"] = 0
            self.stats["distance_traveled_after_departure"] = 0

    def validate_decoys(self):
        rel_lat = self.gt["source"]["latitude"]
        rel_lon = self.gt["source"]["longitude"]
        rel_time = pd.to_datetime(self.gt["source"]["timestamp"])

        for i in range(1, 6):
            did = f"SYNTH-003-DCY0{i}"
            ddf = self.df[self.df["vessel_id"] == did].copy()
            if ddf.empty:
                self.passes[f"DCY0{i}"] = "FAIL"
                continue

            ddf["dist"] = ddf.apply(lambda row: haversine_km(row["latitude"], row["longitude"], rel_lat, rel_lon), axis=1)
            min_dist = ddf["dist"].min()

            if i == 1:
                # DCY01: Passes close, no slowdown
                min_speed = ddf["speed"].min()
                self.passes["DCY01"] = "PASS" if min_dist < 5.0 and min_speed > 6.0 else "FAIL"
            elif i == 2:
                # DCY02: Approaches, slows down, misses source (dist > 1.0)
                min_speed = ddf["speed"].min()
                self.passes["DCY02"] = "PASS" if min_dist > 1.0 and min_dist < 15.0 and min_speed < 8.0 else "FAIL"
            elif i == 3:
                # DCY03: Reaches source region but wrong time
                closest = ddf.loc[ddf["dist"].idxmin()]
                time_diff = abs((closest["timestamp"] - rel_time).total_seconds()) / 3600.0
                self.passes["DCY03"] = "PASS" if min_dist < 5.0 and time_diff > 1.0 else "FAIL"
            elif i == 4:
                # DCY04: Loiters near source but no approach (starts near)
                start_dist = ddf.iloc[0]["dist"]
                min_speed = ddf["speed"].min()
                self.passes["DCY04"] = "PASS" if start_dist < 15.0 and min_speed < 5.0 else "FAIL"
            elif i == 5:
                # DCY05: Approaches correctly but departs before release
                end_time = ddf["timestamp"].max()
                time_diff = (rel_time - end_time).total_seconds() / 60.0
                # Just need to check it departs early. The generator doesn't truncate the trajectory,
                # it just makes it leave. Wait! DCY05 doesn't end early, it just speeds up early!
                # If we want it to literally "depart", we can check if dist at release time is > 2.0.
                exact_or_after = ddf[ddf["timestamp"] >= rel_time]
                dist_at_release = exact_or_after.iloc[0]["dist"] if not exact_or_after.empty else 100.0
                self.passes["DCY05"] = "PASS" if min_dist < 5.0 and dist_at_release > 2.0 else "FAIL"

    def calculate_stats(self):
        self.stats["total_rows"] = len(self.df)
        self.stats["total_vessels"] = self.df["vessel_id"].nunique()
        self.stats["source_rows"] = len(self.df[self.df["vessel_id"] == self.gt["source"]["vessel_id"]])
        decoy_ids = self.gt["candidate_vessels"][1:]
        self.stats["decoy_rows"] = len(self.df[self.df["vessel_id"].isin(decoy_ids)])
        self.stats["background_rows"] = self.stats["total_rows"] - self.stats["source_rows"] - self.stats["decoy_rows"]

        self.stats["min_time"] = self.df["timestamp"].min()
        self.stats["max_time"] = self.df["timestamp"].max()
        self.stats["lat_min"] = self.df["latitude"].min()
        self.stats["lat_max"] = self.df["latitude"].max()
        self.stats["lon_min"] = self.df["longitude"].min()
        self.stats["lon_max"] = self.df["longitude"].max()

        self.stats["avg_speed"] = self.df["speed"].mean()
        self.stats["min_speed"] = self.df["speed"].min()
        self.stats["max_speed"] = self.df["speed"].max()

    def run(self):
        if not self.load():
            return False

        self.validate_data_quality()
        self.validate_source()
        self.validate_decoys()
        self.calculate_stats()

        return True

    def print_report(self):
        print("============================================================")
        print("SCENARIO-003 SYNTHETIC AIS VALIDATION")
        print("============================================================")
        print()
        print(f"Dataset:\n{CSV_PATH.name}")
        print()
        print(f"Scenario:\n{self.gt['scenario_id']}")
        print()
        print(f"Total AIS positions:\n{self.stats['total_rows']}")
        print()
        print(f"Total vessels:\n{self.stats['total_vessels']}")
        print()
        print(f"Source vessel:\n{self.gt['source']['vessel_id']}")
        print()
        print(f"Decoys:\n5")
        print()
        print(f"Background vessels:\n{self.stats['total_vessels'] - 6}")
        print()
        print(f"Time range:\n{self.stats['min_time']} to {self.stats['max_time']}")
        print()
        print(f"Spatial range:\nLat {self.stats['lat_min']:.4f} - {self.stats['lat_max']:.4f}, Lon {self.stats['lon_min']:.4f} - {self.stats['lon_max']:.4f}")
        print()
        print("------------------------------------------------------------")
        print("DATA QUALITY")
        print("------------------------------------------------------------")
        print()
        for k in ["Required columns", "Scenario ID", "Synthetic flags", "Valid coordinates", "Valid timestamps", "Valid speeds", "Valid courses", "Valid headings"]:
            print(f"{k:<20} {self.passes.get(k, 'FAIL')}")

        print()
        print("------------------------------------------------------------")
        print("SOURCE BEHAVIOR")
        print("------------------------------------------------------------")
        print()
        for k in ["Approach", "Slowdown", "Release", "Loiter", "Departure"]:
            print(f"{k:<20} {self.passes.get(k, 'FAIL')}")

        print()
        print("------------------------------------------------------------")
        print("DECOYS")
        print("------------------------------------------------------------")
        print()
        for i in range(1, 6):
            print(f"DCY0{i:<15} {self.passes.get(f'DCY0{i}', 'FAIL')}")

        print()
        print("------------------------------------------------------------")
        all_pass = all(v == "PASS" for v in self.passes.values())
        print(f"\nFINAL RESULT: {'PASS' if all_pass else 'FAIL'}")
        print("============================================================")

    def generate_markdown_report(self):
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

        all_pass = all(v == "PASS" for v in self.passes.values())
        final_verdict = "PASS" if all_pass else "FAIL"

        md = f"""# Scenario-003 Synthetic AIS Validation Report

## 1. Purpose
This dataset provides a highly controlled, synthetic AIS simulation containing one verified source vessel, five specifically engineered decoy vessels, and ~150 background vessels to test vessel attribution mechanics securely isolated from real-world AIS data variations.

## 2. Scenario Configuration
- **Scenario ID**: {self.gt['scenario_id']}
- **Source vessel**: {self.gt['source']['vessel_id']}
- **Decoy count**: 5
- **Background vessel count**: {self.stats['total_vessels'] - 6}
- **Scenario bounds**: Lat {self.stats['lat_min']:.4f} - {self.stats['lat_max']:.4f}, Lon {self.stats['lon_min']:.4f} - {self.stats['lon_max']:.4f}
- **Time range**: {self.stats['min_time']} to {self.stats['max_time']}

## 3. Dataset Statistics
- **Total AIS positions**: {self.stats['total_rows']}
- **Total vessels**: {self.stats['total_vessels']}
- **Rows per vessel**: ~{self.stats['total_rows'] / self.stats['total_vessels']:.1f}
- **Spatial bounds**: Lat {self.stats['lat_min']:.4f} - {self.stats['lat_max']:.4f}, Lon {self.stats['lon_min']:.4f} - {self.stats['lon_max']:.4f}
- **Temporal bounds**: {self.stats['min_time']} to {self.stats['max_time']}
- **Speed statistics**: Avg {self.stats['avg_speed']:.2f}, Min {self.stats['min_speed']:.2f}, Max {self.stats['max_speed']:.2f}

## 4. Source Vessel Behavior
The source vessel exhibited the following calculated metrics:
- **Distance from start to source**: {self.stats.get('distance_start_to_source', 0):.2f} km
- **Speed before slowdown**: {self.stats.get('speed_before_slowdown', 0):.2f} knots
- **Speed during slowdown**: {self.stats.get('speed_during_slowdown', 0):.2f} knots
- **Speed at release**: {self.stats.get('speed_at_release', 0):.2f} knots
- **Minimum distance to release point**: {self.stats.get('minimum_release_area_distance', 0):.4f} km
- **Loiter duration**: {self.stats.get('loiter_duration', 0):.1f} minutes
- **Departure speed**: {self.stats.get('departure_speed', 0):.2f} knots

## 5. Decoy Behavior

| Vessel | Intended Behavior | Result |
|--------|-------------------|--------|
| DCY01  | Passes close at normal speed. No slowdown. | {self.passes.get("DCY01", "FAIL")} |
| DCY02  | Approaches and slows, misses exact source. | {self.passes.get("DCY02", "FAIL")} |
| DCY03  | Reaches source region but at wrong time. | {self.passes.get("DCY03", "FAIL")} |
| DCY04  | Loiters near source, no valid approach. | {self.passes.get("DCY04", "FAIL")} |
| DCY05  | Approaches correctly, departs early. | {self.passes.get("DCY05", "FAIL")} |

## 6. Data Quality

| Check | Result |
|------|--------|
| Required columns | {self.passes.get("Required columns", "FAIL")} |
| Valid coordinates | {self.passes.get("Valid coordinates", "FAIL")} |
| Valid timestamps | {self.passes.get("Valid timestamps", "FAIL")} |
| Valid speeds | {self.passes.get("Valid speeds", "FAIL")} |
| Valid courses | {self.passes.get("Valid courses", "FAIL")} |
| Valid headings | {self.passes.get("Valid headings", "FAIL")} |
| Scenario ID | {self.passes.get("Scenario ID", "FAIL")} |
| Synthetic flags | {self.passes.get("Synthetic flags", "FAIL")} |

## 7. Ground Truth
- **True Source**: {self.gt['source']['vessel_id']}
- **Release Event**: {self.gt['source']['latitude']:.4f}, {self.gt['source']['longitude']:.4f} at {self.gt['source']['timestamp']}

## 8. Visual Validation
See:
- `reports/scenario_003_trajectories.png`
- `reports/scenario_003_source_vs_decoys.png`

## 9. Final Verdict
{final_verdict}
"""
        with REPORT_PATH.open("w", encoding="utf-8") as f:
            f.write(md)


validator_instance = ScenarioValidator()
has_run = False

def get_validator():
    global has_run
    if not CSV_PATH.exists() or not JSON_PATH.exists():
        pytest.skip(f"Synthetic scenario files not found at {CSV_PATH}")
    if not has_run:
        validator_instance.run()
        has_run = True
    return validator_instance

def test_data_quality():
    v = get_validator()
    assert v.passes.get("Required columns") == "PASS"
    assert v.passes.get("Scenario ID") == "PASS"
    assert v.passes.get("Synthetic flags") == "PASS"
    assert v.passes.get("Valid coordinates") == "PASS"
    assert v.passes.get("Valid timestamps") == "PASS"
    assert v.passes.get("Valid speeds") == "PASS"
    assert v.passes.get("Valid courses") == "PASS"
    assert v.passes.get("Valid headings") == "PASS"

def test_source_behavior():
    v = get_validator()
    assert v.passes.get("Approach") == "PASS"
    assert v.passes.get("Slowdown") == "PASS"
    assert v.passes.get("Release") == "PASS"
    assert v.passes.get("Loiter") == "PASS"
    assert v.passes.get("Departure") == "PASS"

def test_decoy_behavior():
    v = get_validator()
    for i in range(1, 6):
        assert v.passes.get(f"DCY0{i}") == "PASS"

if __name__ == "__main__":
    v = get_validator()
    v.print_report()
    v.generate_markdown_report()
