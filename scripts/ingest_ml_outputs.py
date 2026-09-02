from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.schemas import MLPredictionPayload
from app.models.spill import OilSpillDetection


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_INPUT_DIR = Path("json_output")


# ============================================================
# URL NORMALIZATION
# ============================================================

def normalize_image_reference(
    image_reference: str,
) -> str:
    """
    Convert the ML image_reference into a plain URL.

    Supports:

        https://res.cloudinary.com/...

    and Markdown:

        [https://res.cloudinary.com/...](https://res.cloudinary.com/...)
    """

    value = image_reference.strip()

    # Markdown link:
    # [display_text](url)
    markdown_match = re.fullmatch(
        r"\[.*?\]\((https?://[^)]+)\)",
        value,
    )

    if markdown_match:
        return markdown_match.group(1)

    # Already a normal URL
    if value.startswith(("http://", "https://")):
        return value

    raise ValueError(
        f"Invalid image_reference: {image_reference}"
    )

# ============================================================
# TIMESTAMP NORMALIZATION
# ============================================================

def normalize_detected_at(
    detected_at,
):
    """
    ML currently sends timestamps without timezone information.

    Example:

        2019-01-01T03:42:35

    Our historical AIS/environmental data is UTC, so interpret
    naive timestamps as UTC.

    If the timestamp already contains timezone information,
    preserve it.
    """

    if detected_at.tzinfo is None:
        return detected_at.replace(
            tzinfo=timezone.utc
        )

    return detected_at


# ============================================================
# JSON LOADING
# ============================================================

def load_json_file(
    path: Path,
) -> dict:

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# ============================================================
# INGEST ONE FILE
# ============================================================

async def ingest_file(
    db,
    json_path: Path,
    input_root: Path,
    stats: dict,
) -> None:

    stats["files_processed"] += 1

    # --------------------------------------------------------
    # Load JSON
    # --------------------------------------------------------

    try:
        raw_data = load_json_file(
            json_path
        )

    except json.JSONDecodeError as exc:

        stats["files_failed"] += 1

        print(
            f"[FAILED] {json_path}"
        )

        print(
            f"Invalid JSON: {exc}"
        )

        return

    except OSError as exc:

        stats["files_failed"] += 1

        print(
            f"[FAILED] {json_path}"
        )

        print(
            f"Could not read file: {exc}"
        )

        return

    # --------------------------------------------------------
    # Validate ML payload
    # --------------------------------------------------------

    try:

        payload = MLPredictionPayload.model_validate(
            raw_data
        )

    except ValidationError as exc:

        stats["files_failed"] += 1

        print(
            f"[FAILED] {json_path}"
        )

        print(
            "ML schema validation failed:"
        )

        print(exc)

        return

    # --------------------------------------------------------
    # Source image identifier
    # --------------------------------------------------------

    source_image_id = str(
        json_path.relative_to(
            input_root
        )
    )

    # Example:

    # coast/oc-0001.json
    #
    # or
    #
    # water/ow-0001.json

    # --------------------------------------------------------
    # Process every detection
    # --------------------------------------------------------

    for index, detection in enumerate(
        payload.detections,
        start=1,
    ):

        stats["detections_found"] += 1

        # ----------------------------------------------------
        # Check duplicate spill_id
        # ----------------------------------------------------

        result = await db.execute(
            select(
                OilSpillDetection.id
            ).where(
                OilSpillDetection.spill_id
                == detection.spill_id
            )
        )

        existing_id = (
            result.scalar_one_or_none()
        )

        if existing_id is not None:

            stats["already_exists"] += 1

            print(
                f"[SKIP] {detection.spill_id} "
                f"(already exists)"
            )

            continue

        # ----------------------------------------------------
        # Normalize Cloudinary URL
        # ----------------------------------------------------

        try:

            cloudinary_url = (
                normalize_image_reference(
                    detection.image_reference
                )
            )

        except ValueError as exc:

            stats["detections_failed"] += 1

            print(
                f"[FAILED] {json_path} "
                f"detection #{index}"
            )

            print(exc)

            continue

        # ----------------------------------------------------
        # Normalize timestamp
        # ----------------------------------------------------

        detected_at = (
            normalize_detected_at(
                detection.detected_at
            )
        )

        # ----------------------------------------------------
        # Preserve exact individual ML detection
        # ----------------------------------------------------

        raw_detection = (
            raw_data["detections"][index - 1]
        )

        # ----------------------------------------------------
        # Create database row
        # ----------------------------------------------------

        spill = OilSpillDetection(

            spill_id=detection.spill_id,

            detected_at=detected_at,

            centroid_lat=(
                detection.centroid.lat
            ),

            centroid_lon=(
                detection.centroid.lon
            ),

            polygon=detection.polygon,

            area_km2=detection.area_km2,

            estimated_age_hours=(
                detection.estimated_age_hours
            ),

            confidence_score=(
                detection.confidence_score
            ),

            cloudinary_url=cloudinary_url,

            source_image_id=source_image_id,

            raw_prediction=raw_detection,
        )

        db.add(spill)

        stats["inserted"] += 1

        print(
            f"[INSERT] "
            f"{detection.spill_id} "
            f"<- {source_image_id}"
        )

    # --------------------------------------------------------
    # Commit this file
    # --------------------------------------------------------

    try:

        await db.commit()

    except Exception as exc:

        await db.rollback()

        stats["files_failed"] += 1

        print(
            f"[FAILED] Database commit:"
        )

        print(
            f"{json_path}: {exc}"
        )


# ============================================================
# INGEST DIRECTORY
# ============================================================

async def ingest_directory(
    input_dir: Path,
) -> dict:

    if not input_dir.exists():

        raise FileNotFoundError(
            f"Input directory does not exist: "
            f"{input_dir.resolve()}"
        )

    # Recursive search:
    #
    # json_output/coast/*.json
    # json_output/water/*.json

    json_files = sorted(
        input_dir.rglob("*.json")
    )

    print()
    print("=" * 70)
    print("REAL ML OIL-SPILL JSON INGESTION")
    print("=" * 70)

    print(
        f"Input directory : "
        f"{input_dir.resolve()}"
    )

    print(
        f"JSON files found: "
        f"{len(json_files)}"
    )

    print("=" * 70)
    print()

    stats = {
        "files_processed": 0,
        "files_failed": 0,
        "detections_found": 0,
        "detections_failed": 0,
        "inserted": 0,
        "already_exists": 0,
    }

    if not json_files:

        print(
            "No JSON files found."
        )

        return stats

    async with AsyncSessionLocal() as db:

        for json_path in json_files:

            await ingest_file(
                db=db,
                json_path=json_path,
                input_root=input_dir,
                stats=stats,
            )

    return stats


# ============================================================
# CLI
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Ingest real ML oil-spill "
            "JSON outputs into PostgreSQL."
        )
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=(
            "Directory containing ML JSON files. "
            "Default: json_output"
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_args()

    try:

        stats = asyncio.run(
            ingest_directory(
                args.input_dir
            )
        )

    except KeyboardInterrupt:

        print(
            "\nIngestion interrupted."
        )

        return

    except Exception as exc:

        print(
            f"\nFatal error: {exc}"
        )

        raise

    print()
    print("=" * 70)
    print("INGESTION SUMMARY")
    print("=" * 70)

    print(
        f"Files processed     : "
        f"{stats['files_processed']}"
    )

    print(
        f"Files failed        : "
        f"{stats['files_failed']}"
    )

    print(
        f"Detections found    : "
        f"{stats['detections_found']}"
    )

    print(
        f"Detections failed   : "
        f"{stats['detections_failed']}"
    )

    print(
        f"Inserted            : "
        f"{stats['inserted']}"
    )

    print(
        f"Already existed     : "
        f"{stats['already_exists']}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()