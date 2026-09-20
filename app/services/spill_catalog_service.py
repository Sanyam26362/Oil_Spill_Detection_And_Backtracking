import csv
import itertools
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "json_output" / "validation" / "detection_attribution_results.csv"
JSON_OUTPUT_DIR = PROJECT_ROOT / "json_output"

class SpillCatalogService:
    _spills: Dict[str, Dict[str, Any]] = {}
    _initialized = False

    @classmethod
    def initialize(cls):
        """
        Parse the CSV file to find the 97 valid spills with candidate_count > 0.
        Then, load their original polygons and image_references from the source JSON files.
        """
        if cls._initialized:
            return

        if not CSV_PATH.exists():
            # B7: Log instead of print; set _initialized so we don't
            # re-attempt the missing CSV on every subsequent call.
            logger.error("Warning: CSV file not found at %s", CSV_PATH)
            cls._initialized = True
            return

        cls._spills = {}

        # First pass: read CSV and gather the 97 valid spills
        with open(CSV_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                candidate_count_str = row.get("candidate_count", "").strip()
                if not candidate_count_str:
                    continue
                
                try:
                    candidate_count = int(candidate_count_str)
                except ValueError:
                    continue
                
                if candidate_count > 0:
                    spill_id = row["spill_id"]
                    cls._spills[spill_id] = {
                        "spill_id": spill_id,
                        "source_type": row["source_type"],
                        "source_file": row["source_file"],
                        "detected_at": row["detected_at"],
                        "estimated_age_hours": float(row["estimated_age_hours"]),
                        "estimated_release_time": row["estimated_release_time"],
                        "observation_latitude": float(row["observation_latitude"]),
                        "observation_longitude": float(row["observation_longitude"]),
                        "confidence_score": float(row["confidence_score"]),
                        "area_km2": float(row["area_km2"]),
                        "estimated_source_latitude": float(row["estimated_source_latitude"]) if row["estimated_source_latitude"] else None,
                        "estimated_source_longitude": float(row["estimated_source_longitude"]) if row["estimated_source_longitude"] else None,
                        "estimated_source_radius_km": float(row["estimated_source_radius_km"]) if row["estimated_source_radius_km"] else None,
                        "candidate_count": candidate_count,
                        "ranked_top_vessel": row["ranked_top_vessel"] or None,
                        "ranked_top_score": float(row["ranked_top_score"]) if row["ranked_top_score"] else None,
                        "runtime_seconds": float(row["runtime_seconds"]) if row.get("runtime_seconds") else None,
                        "polygon": [],
                        "image_reference": None,
                    }

        # Second pass: read the source JSON files to populate polygon and image_reference
        files_to_read: Dict[str, List[str]] = {}
        for spill_id, spill in cls._spills.items():
            source_type = spill["source_type"]
            source_file = spill["source_file"]
            file_path = JSON_OUTPUT_DIR / source_type / source_file
            
            if str(file_path) not in files_to_read:
                files_to_read[str(file_path)] = []
            files_to_read[str(file_path)].append(spill_id)

        for file_path_str, spill_ids in files_to_read.items():
            path = Path(file_path_str)
            if not path.exists():
                continue
                
            with open(path, mode="r", encoding="utf-8") as f:
                data = json.load(f)
                detections = data.get("detections", [])
                for det in detections:
                    sid = det.get("spill_id")
                    if sid in spill_ids:
                        cls._spills[sid]["polygon"] = det.get("polygon", [])
                        cls._spills[sid]["image_reference"] = det.get("image_reference")

        cls._initialized = True

    @classmethod
    def get_all_spills(cls, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Return paginated list of valid spills."""
        # E6: itertools.islice avoids materialising the whole values list.
        return list(itertools.islice(cls._spills.values(), skip, skip + limit))

    @classmethod
    def get_total_count(cls) -> int:
        """Return total count of valid spills."""
        return len(cls._spills)

    @classmethod
    def get_spill(cls, spill_id: str) -> Dict[str, Any]:
        """Return a single spill by ID, or None if not found."""
        return cls._spills.get(spill_id)

    @classmethod
    def update_spill_attribution(
        cls, spill_id: str, top_vessel: str, top_score: float | None, candidate_count: int
    ) -> None:
        """Update in-memory catalog entry so /vessels and /trajectory match live attribution."""
        if spill_id in cls._spills:
            cls._spills[spill_id]["ranked_top_vessel"] = top_vessel
            cls._spills[spill_id]["ranked_top_score"] = top_score
            cls._spills[spill_id]["candidate_count"] = candidate_count

