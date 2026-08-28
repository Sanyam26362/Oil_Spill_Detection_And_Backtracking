import argparse
import csv
import math
from collections import defaultdict
from datetime import datetime, timezone


EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(
        math.radians,
        [lat1, lon1, lat2, lon2],
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def parse_time(value):
    dt = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def load_ais(path):
    vessels = defaultdict(list)

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row["latitude"] = float(row["latitude"])
            row["longitude"] = float(row["longitude"])
            row["speed"] = float(row["speed"])
            row["timestamp"] = parse_time(row["timestamp"])

            vessels[row["vessel_id"]].append(row)

    for vessel_id in vessels:
        vessels[vessel_id].sort(
            key=lambda x: x["timestamp"]
        )

    return vessels


def distance_from_spill(row, spill_lat, spill_lon):
    return haversine_km(
        row["latitude"],
        row["longitude"],
        spill_lat,
        spill_lon,
    )


def average_speed(rows):
    if not rows:
        return 0.0

    return sum(r["speed"] for r in rows) / len(rows)


def analyze_vessel(rows, spill_lat, spill_lon, spill_time):
    distances = [
        distance_from_spill(
            r,
            spill_lat,
            spill_lon,
        )
        for r in rows
    ]

    min_distance = min(distances)

    closest_index = distances.index(min_distance)
    closest_row = rows[closest_index]

    closest_time = closest_row["timestamp"]

    time_difference_sec = abs(
        (closest_time - spill_time).total_seconds()
    )

    # ---------------------------------------------------------
    # TIME WINDOWS
    # ---------------------------------------------------------

    before_60 = [
        r for r in rows
        if -3600
        <= (r["timestamp"] - spill_time).total_seconds()
        < 0
    ]

    before_30 = [
        r for r in rows
        if -1800
        <= (r["timestamp"] - spill_time).total_seconds()
        < 0
    ]

    event_window = [
        r for r in rows
        if 0
        <= (r["timestamp"] - spill_time).total_seconds()
        <= 1800
        and distance_from_spill(
            r,
            spill_lat,
            spill_lon,
        ) <= 5
    ]

    before_event_near = [
        r for r in rows
        if -1800
        <= (r["timestamp"] - spill_time).total_seconds()
        < 0
        and distance_from_spill(
            r,
            spill_lat,
            spill_lon,
        ) <= 5
    ]

    after_30 = [
        r for r in rows
        if 1800
        < (r["timestamp"] - spill_time).total_seconds()
        <= 3600
    ]

    # ---------------------------------------------------------
    # SPEED
    # ---------------------------------------------------------

    pre_speed = average_speed(before_60)

    pre_event_speed = average_speed(before_event_near)

    event_speed = average_speed(event_window)

    post_speed = average_speed(after_30)

    # ---------------------------------------------------------
    # SPEED REDUCTION
    # ---------------------------------------------------------

    if pre_event_speed > 0:
        slowdown_ratio = (
            pre_event_speed - event_speed
        ) / pre_event_speed

        slowdown_ratio = max(
            0.0,
            min(1.0, slowdown_ratio),
        )
    else:
        slowdown_ratio = 0.0

    # ---------------------------------------------------------
    # LOITERING
    # ---------------------------------------------------------

    loiter_minutes = (
        len(event_window) * 10 / 60
    )

    # ---------------------------------------------------------
    # APPROACH BEHAVIOR
    # ---------------------------------------------------------

    approach_score = 0.0

    if before_event_near:
        earliest_distance = distance_from_spill(
            before_event_near[0],
            spill_lat,
            spill_lon,
        )

        latest_distance = distance_from_spill(
            before_event_near[-1],
            spill_lat,
            spill_lon,
        )

        if earliest_distance > latest_distance:
            approach_score = 1.0

    # ---------------------------------------------------------
    # DEPARTURE
    # ---------------------------------------------------------

    departure_score = 0.0

    if after_30:
        post_distances = [
            distance_from_spill(
                r,
                spill_lat,
                spill_lon,
            )
            for r in after_30
        ]

        if post_distances[-1] > post_distances[0]:
            departure_score = 1.0

    # ---------------------------------------------------------
    # TEMPORAL SCORE
    # ---------------------------------------------------------

    temporal_score = max(
        0.0,
        1.0 - time_difference_sec / 7200,
    )

    # ---------------------------------------------------------
    # PROXIMITY SCORE
    # ---------------------------------------------------------

    proximity_score = max(
        0.0,
        1.0 - min_distance / 10,
    )

    # ---------------------------------------------------------
    # LOITER SCORE
    # ---------------------------------------------------------

    loiter_score = min(
        1.0,
        loiter_minutes / 30,
    )

    # ---------------------------------------------------------
    # COMBINED SCORE
    # ---------------------------------------------------------

    score = (
        proximity_score * 0.25
        + temporal_score * 0.10
        + slowdown_ratio * 0.25
        + loiter_score * 0.20
        + approach_score * 0.10
        + departure_score * 0.10
    )

    if min_distance > 10:
        score = 0.0

    return {
        "min_distance_km": min_distance,
        "time_difference_sec": time_difference_sec,
        "pre_speed": pre_speed,
        "pre_event_speed": pre_event_speed,
        "event_speed": event_speed,
        "post_speed": post_speed,
        "slowdown_ratio": slowdown_ratio,
        "loiter_minutes": loiter_minutes,
        "approach_score": approach_score,
        "departure_score": departure_score,
        "score": score,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Score AIS vessels for oil-spill attribution."
    )

    parser.add_argument(
        "--file",
        required=True,
    )

    parser.add_argument(
        "--spill-lat",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--spill-lon",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--spill-time",
        required=True,
    )

    args = parser.parse_args()

    spill_time = parse_time(args.spill_time)

    vessels = load_ais(args.file)

    results = []

    for vessel_id, rows in vessels.items():

        features = analyze_vessel(
            rows,
            args.spill_lat,
            args.spill_lon,
            spill_time,
        )

        results.append({
            "vessel_id": vessel_id,
            **features,
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    print()
    print("=" * 110)
    print("              AIS VESSEL ATTRIBUTION RESULTS")
    print("=" * 110)

    print(
        f"Spill location: "
        f"{args.spill_lat}, {args.spill_lon}"
    )

    print(f"Spill time: {args.spill_time}")
    print()

    print(
        f"{'Rank':<6}"
        f"{'Vessel':<18}"
        f"{'Score':<9}"
        f"{'Min km':<9}"
        f"{'Time min':<10}"
        f"{'Pre kn':<9}"
        f"{'Event kn':<10}"
        f"{'Slowdown':<10}"
        f"{'Loiter':<9}"
        f"{'Approach':<10}"
        f"{'Depart':<8}"
    )

    print("-" * 110)

    for rank, result in enumerate(
        results[:10],
        1,
    ):
        print(
            f"{rank:<6}"
            f"{result['vessel_id']:<18}"
            f"{result['score']:<9.3f}"
            f"{result['min_distance_km']:<9.3f}"
            f"{result['time_difference_sec'] / 60:<10.1f}"
            f"{result['pre_event_speed']:<9.2f}"
            f"{result['event_speed']:<10.2f}"
            f"{result['slowdown_ratio']:<10.2f}"
            f"{result['loiter_minutes']:<9.1f}"
            f"{result['approach_score']:<10.2f}"
            f"{result['departure_score']:<8.2f}"
        )

    print("=" * 110)


if __name__ == "__main__":
    main()