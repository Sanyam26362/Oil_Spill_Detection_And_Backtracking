import csv
from pathlib import Path
from collections import Counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = (
    PROJECT_ROOT
    / "json_output"
    / "validation"
    / "detection_attribution_results.csv"
)


def main():
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        return

    valid_detections = []

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            candidate_count = row.get("candidate_count", "").strip()

            try:
                candidate_count = int(candidate_count)
            except ValueError:
                continue

            # Same filtering used by SpillCatalogService
            if candidate_count > 0:
                valid_detections.append(row)

    print("=" * 70)
    print("VALID SPILL / VESSEL ANALYSIS")
    print("=" * 70)

    print(f"Total valid detections : {len(valid_detections)}")

    # Get attributed vessel for each detection
    vessels = []

    for row in valid_detections:
        vessel = row.get("ranked_top_vessel", "").strip()

        if vessel:
            vessels.append(vessel)

    counts = Counter(vessels)

    print(f"Detections with vessel : {len(vessels)}")
    print(f"Unique vessels         : {len(counts)}")

    print("\n" + "=" * 70)
    print("DETECTIONS PER VESSEL")
    print("=" * 70)

    for vessel, count in counts.most_common():
        print(f"{vessel:30} -> {count} detection(s)")

    # Repeat vs single-use vessels
    repeat_vessels = {
        vessel: count
        for vessel, count in counts.items()
        if count > 1
    }

    single_vessels = {
        vessel: count
        for vessel, count in counts.items()
        if count == 1
    }

    repeat_detection_count = sum(repeat_vessels.values())

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"Total valid detections              : {len(valid_detections)}")
    print(f"Unique vessels                      : {len(counts)}")
    print(f"Vessels appearing more than once   : {len(repeat_vessels)}")
    print(f"Vessels appearing exactly once     : {len(single_vessels)}")
    print(f"Detections from repeat vessels     : {repeat_detection_count}")
    print(f"Detections from one-time vessels   : {len(single_vessels)}")

    # Show detections with missing vessel attribution
    missing_vessel = len(valid_detections) - len(vessels)

    print(f"Detections without vessel          : {missing_vessel}")


if __name__ == "__main__":
    main()