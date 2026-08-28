import argparse
import csv
import json
import math
import random
from datetime import timedelta
from pathlib import Path

from .scenario import SpillScenario


RANDOM_SEED = 42
random.seed(RANDOM_SEED)

KNOT_TO_KM_PER_SEC = 1.852 / 3600.0


def destination(lat, lon, bearing_deg, distance_km):
    """
    Move from lat/lon by distance_km along bearing_deg.
    """
    earth_radius_km = 6371.0088

    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    bearing = math.radians(bearing_deg)

    angular_distance = distance_km / earth_radius_km

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), math.degrees(lon2)


def haversine_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dlon / 2) ** 2
    )

    return earth_radius_km * 2 * math.asin(math.sqrt(a))


def bearing_between(lat1, lon1, lat2, lon2):
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(lat2)

    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )

    bearing = math.degrees(math.atan2(x, y))

    return (bearing + 360) % 360


def random_vessel_type():
    """
    Weighted toward cargo/tanker traffic because those are useful
    vessel classes for an oil-spill attribution demonstration.
    """
    choices = [
        ("Cargo", 40),
        ("Tanker", 25),
        ("Passenger", 15),
        ("Fishing", 10),
        ("Tug", 5),
        ("Other", 5),
    ]

    values = [x[0] for x in choices]
    weights = [x[1] for x in choices]

    return random.choices(values, weights=weights, k=1)[0]


def random_start_position(scenario):
    return (
        random.uniform(scenario.region_min_lat, scenario.region_max_lat),
        random.uniform(scenario.region_min_lon, scenario.region_max_lon),
    )


def add_record(
    records,
    vessel_id,
    timestamp,
    lat,
    lon,
    speed,
    course,
    heading,
    vessel_type,
    scenario_id,
):
    records.append(
        {
            "vessel_id": vessel_id,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "longitude": round(lon, 7),
            "latitude": round(lat, 7),
            "speed": round(max(0.0, speed), 2),
            "course": round(course % 360, 2),
            "heading": round(heading % 360, 2),
            "vessel_type": vessel_type,
            "country": "SYNTHETIC",
            "is_synthetic": True,
            "scenario_id": scenario_id,
        }
    )


def generate_background_vessel(scenario, vessel_number):
    """
    Generate a normal vessel trajectory.

    These vessels are intentionally unrelated to the spill.
    """
    vessel_id = f"SYNTH-{vessel_number:06d}"

    vessel_type = random_vessel_type()

    start_lat, start_lon = random_start_position(scenario)

    course = random.uniform(0, 360)
    speed = random.uniform(4.0, 16.0)

    timestamp = scenario.origin_time - timedelta(
        hours=scenario.duration_hours / 2
    )

    total_seconds = scenario.duration_hours * 3600
    interval = random.choice([10, 20, 30, 60])

    records = []

    current_lat = start_lat
    current_lon = start_lon

    elapsed = 0

    while elapsed <= total_seconds:
        current_speed = max(
            0.5,
            speed + random.gauss(0, 0.25),
        )

        current_course = (
            course + random.gauss(0, 2.0)
        ) % 360

        heading = current_course + random.gauss(0, 2.0)

        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            current_speed,
            current_course,
            heading,
            vessel_type,
            scenario.scenario_id,
        )

        distance = current_speed * KNOT_TO_KM_PER_SEC * interval

        current_lat, current_lon = destination(
            current_lat,
            current_lon,
            current_course,
            distance,
        )

        timestamp += timedelta(seconds=interval)
        elapsed += interval

    return records


def generate_suspicious_vessel(scenario, vessel_number):
    """
    Generate the ground-truth suspicious vessel.

    Behavior:

        normal approach
            ↓
        slowing down
            ↓
        reaches spill origin around origin_time
            ↓
        loiters near origin
            ↓
        accelerates and departs
    """

    vessel_id = f"SYNTH-{vessel_number:06d}"

    vessel_type = "Tanker"

    origin_lat = scenario.origin_lat
    origin_lon = scenario.origin_lon

    start_time = scenario.origin_time - timedelta(hours=3)
    end_time = scenario.origin_time + timedelta(hours=3)

    # Start approximately 30 km from the spill.
    start_distance_km = 30.0

    # Random approach direction.
    approach_bearing = random.uniform(0, 360)

    start_lat, start_lon = destination(
        origin_lat,
        origin_lon,
        (approach_bearing + 180) % 360,
        start_distance_km,
    )

    records = []

    timestamp = start_time

    # ============================================================
    # PHASE 1 — NORMAL APPROACH
    # ============================================================

    phase_end = scenario.origin_time - timedelta(minutes=90)

    current_lat = start_lat
    current_lon = start_lon

    while timestamp < phase_end:
        course = bearing_between(
            current_lat,
            current_lon,
            origin_lat,
            origin_lon,
        )

        speed = 10.0 + random.gauss(0, 0.25)

        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            speed,
            course,
            course + random.gauss(0, 1.5),
            vessel_type,
            scenario.scenario_id,
        )

        interval = 10

        distance = speed * KNOT_TO_KM_PER_SEC * interval

        current_lat, current_lon = destination(
            current_lat,
            current_lon,
            course,
            distance,
        )

        timestamp += timedelta(seconds=interval)

    # ============================================================
    # PHASE 2 — SLOWDOWN
    # ============================================================

    phase_end = scenario.origin_time - timedelta(minutes=20)

    while timestamp < phase_end:
        course = bearing_between(
            current_lat,
            current_lon,
            origin_lat,
            origin_lon,
        )

        speed = 3.0 + random.gauss(0, 0.15)

        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            speed,
            course,
            course + random.gauss(0, 1.0),
            vessel_type,
            scenario.scenario_id,
        )

        interval = 10

        distance = speed * KNOT_TO_KM_PER_SEC * interval

        current_lat, current_lon = destination(
            current_lat,
            current_lon,
            course,
            distance,
        )

        timestamp += timedelta(seconds=interval)

    # ============================================================
    # PHASE 3 — ARRIVE AT SPILL ORIGIN
    # ============================================================

    # Explicitly place the vessel at the spill origin.
    current_lat = origin_lat
    current_lon = origin_lon

    while timestamp < scenario.origin_time:
        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            1.2 + random.gauss(0, 0.1),
            approach_bearing,
            approach_bearing,
            vessel_type,
            scenario.scenario_id,
        )

        timestamp += timedelta(seconds=10)

    # Guarantee an observation at the exact spill time.
    add_record(
        records,
        vessel_id,
        scenario.origin_time,
        origin_lat,
        origin_lon,
        0.8,
        approach_bearing,
        approach_bearing,
        vessel_type,
        scenario.scenario_id,
    )

    # ============================================================
    # PHASE 4 — LOITER NEAR SPILL
    # ============================================================

    phase_end = scenario.origin_time + timedelta(minutes=30)

    while timestamp < phase_end:
        # Small movement around the origin.
        angle = random.uniform(0, 360)
        radius = random.uniform(0.05, 0.25)

        current_lat, current_lon = destination(
            origin_lat,
            origin_lon,
            angle,
            radius,
        )

        speed = random.uniform(0.5, 1.8)

        course = random.uniform(0, 360)

        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            speed,
            course,
            course + random.gauss(0, 3),
            vessel_type,
            scenario.scenario_id,
        )

        timestamp += timedelta(seconds=10)

    # ============================================================
    # PHASE 5 — DEPARTURE
    # ============================================================

    current_lat = origin_lat
    current_lon = origin_lon

    departure_course = (approach_bearing + 180) % 360

    phase_end = end_time

    while timestamp <= phase_end:
        # Gradually accelerate after the spill.
        minutes_after = (
            timestamp - (scenario.origin_time + timedelta(minutes=30))
        ).total_seconds() / 60

        speed = min(
            11.0,
            2.0 + max(0, minutes_after) * 0.12,
        )

        speed += random.gauss(0, 0.2)

        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            speed,
            departure_course,
            departure_course + random.gauss(0, 1.5),
            vessel_type,
            scenario.scenario_id,
        )

        interval = 10

        distance = speed * KNOT_TO_KM_PER_SEC * interval

        current_lat, current_lon = destination(
            current_lat,
            current_lon,
            departure_course,
            distance,
        )

        timestamp += timedelta(seconds=interval)

    return records


def generate_decoy_vessel(scenario, vessel_number, decoy_index):
    """
    Generate plausible vessels that should not win attribution.

    Different decoys fail for different reasons:

    0 -> close to spill but wrong timing
    1 -> correct timing but remains too far away
    2 -> passes near spill at normal speed
    3 -> slows down but at the wrong location
    4 -> close to spill but does not loiter
    """

    vessel_id = f"SYNTH-{vessel_number:06d}"

    vessel_type = random.choice(
        ["Cargo", "Tanker", "Cargo", "Passenger"]
    )

    origin_lat = scenario.origin_lat
    origin_lon = scenario.origin_lon

    records = []

    timestamp = scenario.origin_time - timedelta(hours=3)

    total_seconds = 6 * 3600

    # ------------------------------------------------------------
    # Decoy 0: reaches spill early
    # ------------------------------------------------------------

    if decoy_index == 0:
        start_distance = 25
        bearing = 45
        speed = 10.0

    # ------------------------------------------------------------
    # Decoy 1: timing is correct but distance is ~15 km
    # ------------------------------------------------------------

    elif decoy_index == 1:
        start_distance = 35
        bearing = 90
        speed = 9.0

    # ------------------------------------------------------------
    # Decoy 2: crosses spill at normal speed
    # ------------------------------------------------------------

    elif decoy_index == 2:
        start_distance = 30
        bearing = 180
        speed = 11.0

    # ------------------------------------------------------------
    # Decoy 3: slows down, but far away
    # ------------------------------------------------------------

    elif decoy_index == 3:
        start_distance = 45
        bearing = 270
        speed = 8.0

    # ------------------------------------------------------------
    # Decoy 4: passes near spill but does not loiter
    # ------------------------------------------------------------

    else:
        start_distance = 28
        bearing = 135
        speed = 10.5

    start_lat, start_lon = destination(
        origin_lat,
        origin_lon,
        bearing,
        start_distance,
    )

    current_lat = start_lat
    current_lon = start_lon

    while timestamp <= scenario.origin_time + timedelta(hours=3):

        course = bearing_between(
            current_lat,
            current_lon,
            origin_lat,
            origin_lon,
        )

        # Different behavior around the spill time.
        minutes_from_origin = (
            timestamp - scenario.origin_time
        ).total_seconds() / 60

        if decoy_index == 3 and -20 <= minutes_from_origin <= 30:
            current_speed = 1.5
        else:
            current_speed = speed + random.gauss(0, 0.25)

        add_record(
            records,
            vessel_id,
            timestamp,
            current_lat,
            current_lon,
            current_speed,
            course,
            course + random.gauss(0, 2),
            vessel_type,
            scenario.scenario_id,
        )

        interval = 10

        distance = current_speed * KNOT_TO_KM_PER_SEC * interval

        current_lat, current_lon = destination(
            current_lat,
            current_lon,
            course,
            distance,
        )

        timestamp += timedelta(seconds=interval)

    return records


def build_scenario():
    return SpillScenario(
        scenario_id="scenario-001",

        origin_lat=33.50,
        origin_lon=34.00,

        origin_time=__import__("datetime").datetime(
            2019,
            7,
            15,
            12,
            0,
            0,
        ),

        region_min_lat=30.0,
        region_max_lat=37.0,

        region_min_lon=30.0,
        region_max_lon=36.0,

        duration_hours=6,

        background_vessels=10,
        candidate_vessels=5,

        suspicious_vessel_index=0,
    )


def generate_dataset(scenario):
    records = []

    # Background vessels.
    for i in range(1, scenario.background_vessels + 1):
        records.extend(
            generate_background_vessel(
                scenario,
                i,
            )
        )

    # Candidate vessel IDs start after background vessels.
    first_candidate_id = scenario.background_vessels + 1

    for candidate_index in range(scenario.candidate_vessels):

        vessel_number = first_candidate_id + candidate_index

        if candidate_index == scenario.suspicious_vessel_index:
            candidate_records = generate_suspicious_vessel(
                scenario,
                vessel_number,
            )
        else:
            candidate_records = generate_decoy_vessel(
                scenario,
                vessel_number,
                candidate_index,
            )

        records.extend(candidate_records)

    records.sort(
        key=lambda r: (
            r["timestamp"],
            r["vessel_id"],
        )
    )

    return records


def write_csv(records, output_path):
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "vessel_id",
        "timestamp",
        "longitude",
        "latitude",
        "speed",
        "course",
        "heading",
        "vessel_type",
        "country",
        "is_synthetic",
        "scenario_id",
    ]

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(records)


def write_ground_truth(scenario, output_path):
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    suspicious_number = (
        scenario.background_vessels
        + 1
        + scenario.suspicious_vessel_index
    )

    ground_truth = {
        "scenario_id": scenario.scenario_id,
        "synthetic": True,
        "spill": {
            "latitude": scenario.origin_lat,
            "longitude": scenario.origin_lon,
            "timestamp": scenario.origin_time.isoformat() + "Z",
        },
        "ground_truth_suspicious_vessel": (
            f"SYNTH-{suspicious_number:06d}"
        ),
        "candidate_vessels": [
            f"SYNTH-{scenario.background_vessels + i + 1:06d}"
            for i in range(scenario.candidate_vessels)
        ],
        "expected_behavior": {
            "approach": True,
            "slowdown_near_origin": True,
            "loiter_near_origin": True,
            "departure_after_event": True,
        },
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            ground_truth,
            f,
            indent=2,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic AIS data."
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path.",
    )

    parser.add_argument(
        "--ground-truth",
        default="data/ais/processed/synthetic_ground_truth.json",
        help="Ground truth JSON path.",
    )

    args = parser.parse_args()

    scenario = build_scenario()

    records = generate_dataset(scenario)

    output_path = Path(args.output)

    ground_truth_path = Path(args.ground_truth)

    write_csv(
        records,
        output_path,
    )

    write_ground_truth(
        scenario,
        ground_truth_path,
    )

    suspicious_number = (
        scenario.background_vessels
        + 1
        + scenario.suspicious_vessel_index
    )

    print()
    print("Synthetic AIS generation complete.")
    print(f"Scenario: {scenario.scenario_id}")
    print(f"Records: {len(records):,}")
    print(f"Output: {output_path}")
    print(
        "Ground-truth suspicious vessel: "
        f"SYNTH-{suspicious_number:06d}"
    )
    print(f"Ground truth: {ground_truth_path}")


if __name__ == "__main__":
    main()