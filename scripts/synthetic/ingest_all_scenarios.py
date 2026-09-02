import os
import subprocess
from pathlib import Path

scripts_dir = Path("scripts/synthetic")
data_dir = Path("data/ais/processed")

scenarios = [
    "synthetic_scenario_001",
    "synthetic_scenario_002",
    "synthetic_scenario_003",
    "synthetic_scenario_004",
    "synthetic_scenario_005",
]

for s in scenarios:
    csv_file = data_dir / f"{s}.csv"
    gt_file = data_dir / f"{s}_ground_truth.json"

    print(f"Ingesting {s}...")
    try:
        subprocess.run([
            ".venv\\Scripts\\python.exe",
            str(scripts_dir / "ingest_synthetic.py"),
            "--csv", str(csv_file),
            "--ground-truth", str(gt_file)
        ], check=True)
        print(f"Successfully ingested {s}.")
    except subprocess.CalledProcessError as e:
        print(f"Error ingesting {s}: {e}")
        break

print("All scenarios ingested!")
