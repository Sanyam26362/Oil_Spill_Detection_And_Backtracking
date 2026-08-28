import re

with open("scripts/synthetic/generate_synthetic_ais.py", "r", encoding="utf-8") as f:
    content = f.read()

pattern = re.compile(r"def generate_decoy_vessel\(.*?(?=# -------------------------------------------------------------------\n# DATASET)", re.DOTALL)

new_func = """def generate_decoy_vessel(
    scenario: SyntheticScenarioConfig,
    decoy_index: int,
    rng: np.random.Generator,
) -> pd.DataFrame:

    release_time = utc_timestamp(scenario.release_time)
    start_time = release_time - pd.Timedelta(hours=4)
    end_time = release_time + pd.Timedelta(hours=6)

    vessel_id = f"SYNTH-{scenario.decoy_start_id + decoy_index:06d}"
    vessel_type = ["Tanker", "Cargo", "Tanker", "Passenger", "Tanker", "Fishing"][decoy_index % 6]

    b_type = decoy_index % 6
    
    target_time = release_time
    target_lat = scenario.release_lat
    target_lon = scenario.release_lon
    target_speed = 12.0
    slowdown = False
    loiter = False

    if b_type == 0:
        target_lat += rng.uniform(-0.02, 0.02)
        target_lon += rng.uniform(-0.02, 0.02)
        target_speed = rng.uniform(12.0, 16.0)
    elif b_type == 1:
        target_lat += rng.uniform(0.03, 0.06) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.03, 0.06) * rng.choice([-1, 1])
        target_speed = 4.0
        slowdown = True
    elif b_type == 2:
        target_time = release_time - pd.Timedelta(hours=rng.uniform(1.5, 3.0))
        target_speed = rng.uniform(10.0, 14.0)
    elif b_type == 3:
        target_lat += rng.uniform(0.04, 0.08) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.04, 0.08) * rng.choice([-1, 1])
        target_speed = 1.0
        loiter = True
    elif b_type == 4:
        target_lat += rng.uniform(-0.05, 0.05)
        target_lon += rng.uniform(-0.05, 0.05)
        target_speed = rng.uniform(11.0, 15.0)
    else:
        target_lat += rng.uniform(0.08, 0.12) * rng.choice([-1, 1])
        target_lon += rng.uniform(0.08, 0.12) * rng.choice([-1, 1])
        target_speed = 1.0
        slowdown = True
        loiter = True

    seconds_to_target = (target_time - start_time).total_seconds()
    approach_speed = 12.0 if slowdown or loiter else target_speed
    
    distance_km = (approach_speed * 1.852 * seconds_to_target) / 3600.0
    angle = rng.uniform(0, 360)
    bearing = (angle + 180) % 360

    angular_distance = distance_km / 6371.0088
    lat1 = math.radians(target_lat)
    lon1 = math.radians(target_lon)
    b_rad = math.radians(angle)
    lat2 = math.asin(math.sin(lat1) * math.cos(angular_distance) + math.cos(lat1) * math.sin(angular_distance) * math.cos(b_rad))
    lon2 = lon1 + math.atan2(math.sin(b_rad) * math.sin(angular_distance) * math.cos(lat1), math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2))
    
    current_lat = math.degrees(lat2)
    current_lon = math.degrees(lon2)
    current_time = start_time

    records = []

    while current_time <= end_time:
        course = bearing_between(current_lat, current_lon, target_lat, target_lon)
        minutes_from_target = (current_time - target_time).total_seconds() / 60.0
        
        if slowdown and -40 <= minutes_from_target <= 0:
            speed = max(target_speed, approach_speed - (approach_speed - target_speed) * (40 + minutes_from_target)/40.0)
        elif loiter and 0 < minutes_from_target <= 40:
            speed = max(0.5, rng.normal(1.0, 0.2))
            course = rng.uniform(0, 360)
        elif minutes_from_target > 0:
            speed = approach_speed
            course = bearing
        else:
            speed = approach_speed
            
        interval = sample_reporting_interval(rng, moving=(speed > 3.0))
        
        distance_to_target = haversine_km(current_lat, current_lon, target_lat, target_lon)
        max_dist = speed * 1.852 * interval / 3600.0
        
        if minutes_from_target <= 0 and max_dist >= distance_to_target:
            interval = max(1, int((target_time - current_time).total_seconds()))
            if interval > 0:
                speed = (distance_to_target * 3600.0) / (interval * 1.852)
            current_lat = target_lat
            current_lon = target_lon
            course = bearing
        else:
            current_lat, current_lon = move_vessel(current_lat, current_lon, course, speed, interval)
            
        add_record(
            records, vessel_id, current_time, current_lat, current_lon,
            speed + rng.normal(0, 0.15), course, course + rng.normal(0, 1),
            vessel_type, "UN", scenario.scenario_id
        )

        current_time += pd.Timedelta(seconds=interval)

    return pd.DataFrame(records)

"""

new_content = pattern.sub(new_func, content)

with open("scripts/synthetic/generate_synthetic_ais.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Decoys updated.")
