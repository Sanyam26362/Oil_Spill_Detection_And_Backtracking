import json
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CSV_PATH = PROJECT_ROOT / "data/ais/processed/synthetic_scenario_003.csv"
JSON_PATH = PROJECT_ROOT / "data/ais/processed/synthetic_scenario_003_ground_truth.json"
PLOT_FULL_PATH = PROJECT_ROOT / "reports/scenario_003_trajectories.png"
PLOT_ZOOM_PATH = PROJECT_ROOT / "reports/scenario_003_source_vs_decoys.png"

def main():
    if not CSV_PATH.exists() or not JSON_PATH.exists():
        print("Data not found. Run scenario generator first.")
        return

    df = pd.read_csv(CSV_PATH)
    with open(JSON_PATH, "r") as f:
        gt = json.load(f)

    source_id = gt["source"]["vessel_id"]
    decoy_ids = set(gt["candidate_vessels"]) - {source_id}
    
    release_lat = gt["source"]["latitude"]
    release_lon = gt["source"]["longitude"]

    # Plot Full Trajectories
    fig, ax = plt.subplots(figsize=(12, 10))
    
    for vid, group in df.groupby("vessel_id"):
        if vid == source_id:
            continue
        if vid in decoy_ids:
            continue
        ax.plot(group["longitude"], group["latitude"], color="lightgray", linewidth=0.5, alpha=0.5)

    for vid in decoy_ids:
        group = df[df["vessel_id"] == vid]
        ax.plot(group["longitude"], group["latitude"], linestyle="--", linewidth=1.5, label=vid)
        
    src_group = df[df["vessel_id"] == source_id]
    ax.plot(src_group["longitude"], src_group["latitude"], color="red", linewidth=2.5, label="Source")
    
    ax.scatter(release_lon, release_lat, color="black", marker="X", s=100, label="Release Event", zorder=10)
    
    ax.set_title("Scenario-003: All Trajectories")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1))
    
    plt.tight_layout()
    PLOT_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT_FULL_PATH, dpi=150)
    plt.close(fig)

    # Plot Zoomed (Source vs Decoys)
    fig, ax = plt.subplots(figsize=(10, 8))
    
    for vid in decoy_ids:
        group = df[df["vessel_id"] == vid]
        ax.plot(group["longitude"], group["latitude"], marker=".", linestyle="--", linewidth=1.5, label=vid)
        
    ax.plot(src_group["longitude"], src_group["latitude"], color="red", marker="o", markersize=4, linewidth=2.5, label="Source")
    
    ax.scatter(release_lon, release_lat, color="black", marker="X", s=150, label="Release Event", zorder=10)
    
    ax.set_xlim(release_lon - 0.1, release_lon + 0.1)
    ax.set_ylim(release_lat - 0.1, release_lat + 0.1)
    
    ax.set_title("Scenario-003: Source vs Decoys (Zoomed)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1))
    
    plt.tight_layout()
    fig.savefig(PLOT_ZOOM_PATH, dpi=150)
    plt.close(fig)
    
    print("Plots generated:")
    print(f"- {PLOT_FULL_PATH}")
    print(f"- {PLOT_ZOOM_PATH}")

if __name__ == "__main__":
    main()
