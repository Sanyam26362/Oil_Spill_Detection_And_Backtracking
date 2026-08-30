import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from scripts.synthetic.yearly_config import YearlyAISConfig
def _haversine_vectorized(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

def calculate_implied_speeds(lats, lons, times):
    # times is a series of datetime
    # Returns implied speeds in knots between consecutive points
    if len(lats) < 2:
        return np.array([])
    
    dists_km = _haversine_vectorized(lats[:-1].values, lons[:-1].values, lats[1:].values, lons[1:].values)
    dt_seconds = (times.iloc[1:].values - times.iloc[:-1].values).astype('timedelta64[s]').astype(float)
    
    # Avoid div by zero if any duplicates exist (though they shouldn't)
    dt_seconds[dt_seconds == 0] = 1e-9
    
    speed_ms = (dists_km * 1000) / dt_seconds
    speed_knots = speed_ms * 1.94384
    return speed_knots

def main():
    config = YearlyAISConfig()
    OUTPUT_DIR = PROJECT_ROOT / "data" / "ais" / "processed" / "yearly"
    
    if len(sys.argv) > 1:
        months_to_test = [int(m) for m in sys.argv[1].split("-")]
        if len(months_to_test) == 1:
            start_m, end_m = months_to_test[0], months_to_test[0]
        else:
            start_m, end_m = months_to_test[0], months_to_test[1]
    else:
        start_m, end_m = 1, 12
    
    print(f"Validating months: {start_m} to {end_m}")
    
    all_vessel_ids = None
    
    last_points = {} # vessel_id -> (lat, lon, time)
    
    total_records = 0
    total_dupes = 0
    total_id_time_dupes = 0
    
    missing_heading = 0
    missing_course = 0
    missing_speed = 0
    
    all_speeds = []
    cross_month_speeds = []
    intervals = []
    
    for month in range(start_m, end_m + 1):
        file_path = OUTPUT_DIR / f"synthetic_ais_{config.year}-{month:02d}.csv"
        if not file_path.exists():
            print(f"ERROR: File {file_path} does not exist.")
            sys.exit(1)
            
        print(f"\n--- Loading Month {month:02d} ---")
        df = pd.read_csv(file_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # B. Vessel count
        vessel_ids = set(df['vessel_id'].unique())
        print(f"Vessels in month: {len(vessel_ids)}")
        if len(vessel_ids) != 200:
            print(f"ERROR: Expected 200 vessels, found {len(vessel_ids)}")
            
        # C. Persistent IDs
        if all_vessel_ids is None:
            all_vessel_ids = vessel_ids
        else:
            if vessel_ids != all_vessel_ids:
                print("ERROR: Vessel IDs changed across months!")
                diff = vessel_ids.symmetric_difference(all_vessel_ids)
                print(f"Diff: {diff}")
        
        # D. Required fields
        expected_cols = ["timestamp", "vessel_id", "latitude", "longitude", "speed", "course", "heading", "vessel_type", "country", "is_synthetic", "scenario_id"]
        missing_cols = [c for c in expected_cols if c not in df.columns]
        if missing_cols:
            print(f"ERROR: Missing columns: {missing_cols}")
            
        # E. Missing values
        mh = df['heading'].isna().sum()
        mc = df['course'].isna().sum()
        ms = df['speed'].isna().sum()
        missing_heading += mh
        missing_course += mc
        missing_speed += ms
        print(f"Missing Heading: {mh/len(df)*100:.2f}% | Course: {mc/len(df)*100:.2f}% | Speed: {ms/len(df)*100:.2f}%")
        
        # F. Duplicate rows
        dupes = df.duplicated().sum()
        id_time_dupes = df.duplicated(subset=['vessel_id', 'timestamp']).sum()
        total_dupes += dupes
        total_id_time_dupes += id_time_dupes
        print(f"Exact duplicates: {dupes}, ID+Time duplicates: {id_time_dupes}")
        
        # G. Geographic bounds
        out_of_bounds = df[(df['latitude'] < config.region_min_lat) | (df['latitude'] > config.region_max_lat) | (df['longitude'] < config.region_min_lon) | (df['longitude'] > config.region_max_lon)]
        if len(out_of_bounds) > 0:
            print(f"ERROR: {len(out_of_bounds)} points out of bounds!")
            
        # Sort by vessel_id and timestamp
        df = df.sort_values(['vessel_id', 'timestamp'])
        
        total_records += len(df)
        
        # Calculate kinematics
        grouped = df.groupby('vessel_id')
        
        month_implied_speeds = []
        month_intervals = []
        
        for vid, group in grouped:
            times = group['timestamp']
            lats = group['latitude']
            lons = group['longitude']
            
            # Check L. Temporal ordering
            if not times.is_monotonic_increasing:
                print(f"ERROR: Timestamps not strictly increasing for vessel {vid}")
                
            speeds = calculate_implied_speeds(lats, lons, times)
            month_implied_speeds.extend(speeds)
            
            ivs = (times.iloc[1:].values - times.iloc[:-1].values).astype('timedelta64[s]').astype(float)
            month_intervals.extend(ivs)
            
            # K. Cross month continuity
            if vid in last_points:
                last_lat, last_lon, last_time = last_points[vid]
                first_lat, first_lon, first_time = lats.iloc[0], lons.iloc[0], times.iloc[0]
                
                # Combine last point of previous month with first point of this month
                x_speeds = calculate_implied_speeds(
                    pd.Series([last_lat, first_lat]),
                    pd.Series([last_lon, first_lon]),
                    pd.Series([last_time, first_time])
                )
                if len(x_speeds) > 0:
                    cross_month_speeds.append(x_speeds[0])
                    
            last_points[vid] = (lats.iloc[-1], lons.iloc[-1], times.iloc[-1])
            
        if month_implied_speeds:
            print(f"Max implied speed (within month): {np.max(month_implied_speeds):.2f} kn")
        if cross_month_speeds:
            print(f"Max cross-month implied speed (so far): {np.max(cross_month_speeds):.2f} kn")
            
        all_speeds.extend(month_implied_speeds)
        intervals.extend(month_intervals)
        
    print("\n=======================================================")
    print("FINAL SUMMARY")
    print("=======================================================")
    print(f"Total Records: {total_records}")
    print(f"Total Duplicates: {total_dupes}")
    print(f"Total ID+Time Duplicates: {total_id_time_dupes}")
    print(f"Global Missing Heading: {missing_heading/total_records*100:.2f}%")
    print(f"Global Missing Course: {missing_course/total_records*100:.2f}%")
    print(f"Global Missing Speed: {missing_speed/total_records*100:.2f}%")
    print(f"Intervals - min: {np.min(intervals)}, median: {np.median(intervals)}, mean: {np.mean(intervals):.2f}, p90: {np.percentile(intervals, 90)}, p95: {np.percentile(intervals, 95)}, max: {np.max(intervals)}")
    print(f"Implied Speed (all) - Max: {np.max(all_speeds):.2f} kn")
    print(f"Implied Speed (all) - Count > 40kn: {np.sum(np.array(all_speeds) > 40)}")
    print(f"Implied Speed (all) - Count > 60kn: {np.sum(np.array(all_speeds) > 60)}")
    print(f"Implied Speed (all) - Count > 100kn: {np.sum(np.array(all_speeds) > 100)}")
    if cross_month_speeds:
        print("\n--- Cross Month Continuity ---")
        print(f"Count of cross-month segments: {len(cross_month_speeds)}")
        print(f"Max implied speed: {np.max(cross_month_speeds):.2f} kn")
        print(f"Count > 40kn: {np.sum(np.array(cross_month_speeds) > 40)}")
        print(f"Count > 60kn: {np.sum(np.array(cross_month_speeds) > 60)}")
        print(f"Count > 100kn: {np.sum(np.array(cross_month_speeds) > 100)}")

if __name__ == "__main__":
    main()
