import json
from pathlib import Path

for sample_path in [
    Path("json_output/coast/oc-0001.json"),
    Path("json_output_water/ow-0001.json"),
]:
    if sample_path.exists():
        with open(sample_path) as f:
            data = json.load(f)
        print(f"=== {sample_path} ===")
        print(json.dumps(data, indent=2)[:500])  # First 500 characters
    else:
        print(f"File not found: {sample_path}")