import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.ais import AISPosition, Vessel


STATIC_FILE = Path(
    "data/ais/raw/piraeus/static/ais_static/unipi_ais_static.csv"
)

CODES_FILE = Path(
    "data/ais/raw/piraeus/static/ais_static/ais_codes_descriptions.csv"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import Piraeus AIS dynamic data into PostGIS."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to a Piraeus dynamic AIS CSV file.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of AIS records to import.",
    )

    return parser.parse_args()


def load_ship_types():
    ship_types = {}

    with CODES_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            try:
                code = int(row["Type Code"])
            except (ValueError, TypeError):
                continue

            ship_types[code] = row["Description"]

    return ship_types


def load_vessel_metadata():
    metadata = {}

    with STATIC_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            vessel_id = row["vessel_id"]

            raw_shiptype = row.get("shiptype", "").strip()

            shiptype = None

            if raw_shiptype:

                try:
                    value = int(float(raw_shiptype))

                    if 0 <= value <= 99:
                        shiptype = value

                except ValueError:
                    shiptype = None

            metadata[vessel_id] = {
                "country": row.get("country") or None,
                "shiptype": shiptype,
            }

    return metadata


def timestamp_to_utc(timestamp_ms: str) -> datetime:
    return datetime.fromtimestamp(
        int(timestamp_ms) / 1000,
        tz=timezone.utc,
    )


async def get_or_create_vessel(
    db: AsyncSession,
    vessel_id: str,
    metadata: dict,
    ship_types: dict,
    vessel_cache: dict,
):
    if vessel_id in vessel_cache:
        return vessel_cache[vessel_id]

    result = await db.execute(
        select(Vessel).where(
            Vessel.vessel_id == vessel_id
        )
    )

    vessel = result.scalar_one_or_none()

    if vessel is None:

        info = metadata.get(vessel_id, {})

        shiptype = info.get("shiptype")

        shiptype_name = None

        if shiptype is not None:
            shiptype_name = ship_types.get(shiptype)

        vessel = Vessel(
            vessel_id=vessel_id,
            country=info.get("country"),
            shiptype=shiptype,
            shiptype_name=shiptype_name,
        )

        db.add(vessel)

    vessel_cache[vessel_id] = vessel

    return vessel


async def ingest(
    file_path: Path,
    limit: int | None,
):

    print("Loading static vessel metadata...")

    metadata = load_vessel_metadata()

    ship_types = load_ship_types()

    print(
        f"Static vessel records loaded: "
        f"{len(metadata):,}"
    )

    print()
    print("Starting AIS ingestion...")
    print(f"File: {file_path}")

    if limit is not None:
        print(f"Limit: {limit:,}")

    print()

    imported = 0
    skipped = 0
    vessels_created = 0

    vessel_cache = {}

    async with AsyncSessionLocal() as db:

        try:

            with file_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as file:

                reader = csv.DictReader(file)

                for row in reader:

                    if limit is not None and imported >= limit:
                        break

                    try:

                        vessel_id = row["vessel_id"]

                        timestamp = timestamp_to_utc(
                            row["t"]
                        )

                        longitude = float(
                            row["lon"]
                        )

                        latitude = float(
                            row["lat"]
                        )

                        if not (
                            -180 <= longitude <= 180
                            and
                            -90 <= latitude <= 90
                        ):
                            skipped += 1
                            continue

                        speed = (
                            float(row["speed"])
                            if row["speed"]
                            else None
                        )

                        course = (
                            float(row["course"])
                            if row["course"]
                            else None
                        )

                        heading = (
                            float(row["heading"])
                            if row["heading"]
                            else None
                        )

                        # Create geographic Point.
                        # IMPORTANT: GeoJSON/PostGIS convention:
                        # X = longitude
                        # Y = latitude
                        point = Point(
                            longitude,
                            latitude,
                        )

                        vessel_before = (
                            vessel_id
                            in vessel_cache
                        )

                        await get_or_create_vessel(
                            db=db,
                            vessel_id=vessel_id,
                            metadata=metadata,
                            ship_types=ship_types,
                            vessel_cache=vessel_cache,
                        )

                        if (
                            not vessel_before
                            and vessel_id not in vessel_cache
                        ):
                            vessels_created += 1

                        ais_position = AISPosition(
                            vessel_id=vessel_id,
                            timestamp=timestamp,
                            longitude=longitude,
                            latitude=latitude,
                            speed=speed,
                            course=course,
                            heading=heading,
                            geometry=from_shape(
                                point,
                                srid=4326,
                            ),
                            is_synthetic=False,
                        )

                        db.add(ais_position)

                        imported += 1

                        if imported % 1000 == 0:

                            await db.commit()

                            print(
                                f"Imported "
                                f"{imported:,} AIS records..."
                            )

                    except (
                        ValueError,
                        KeyError,
                        TypeError,
                    ) as exc:

                        skipped += 1

                        print(
                            f"Skipping invalid row: "
                            f"{exc}"
                        )

            await db.commit()

            print()
            print("========== IMPORT COMPLETE ==========")
            print(
                f"AIS records imported: "
                f"{imported:,}"
            )
            print(
                f"Rows skipped: "
                f"{skipped:,}"
            )
            print(
                f"Unique vessels encountered: "
                f"{len(vessel_cache):,}"
            )
            print("======================================")

        except Exception:

            await db.rollback()

            raise


async def main():

    args = parse_args()

    file_path = Path(args.file)

    if not file_path.exists():
        raise FileNotFoundError(
            f"AIS file not found: {file_path}"
        )

    await ingest(
        file_path=file_path,
        limit=args.limit,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())