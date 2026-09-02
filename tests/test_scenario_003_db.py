from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import engine


async def main() -> None:
    scenario_id = "scenario-003"

    async with engine.connect() as db:
        print("=" * 80)
        print("SCENARIO-003 DATABASE VALIDATION")
        print("=" * 80)

        # ---------------------------------------------------------------
        # Overall scenario statistics
        # ---------------------------------------------------------------
        result = await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS positions,
                    COUNT(DISTINCT vessel_id) AS vessels,
                    COUNT(*) FILTER (WHERE is_synthetic = TRUE)
                        AS synthetic_positions,
                    MIN(timestamp) AS start_time,
                    MAX(timestamp) AS end_time
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                """
            ),
            {"scenario_id": scenario_id},
        )

        row = result.fetchone()

        print()
        print("SCENARIO STATISTICS")
        print("-" * 80)
        print(f"Positions          : {row.positions}")
        print(f"Vessels            : {row.vessels}")
        print(f"Synthetic positions: {row.synthetic_positions}")
        print(f"Start time         : {row.start_time}")
        print(f"End time           : {row.end_time}")

        # ---------------------------------------------------------------
        # Source vessel
        # ---------------------------------------------------------------
        result = await db.execute(
            text(
                """
                SELECT
                    vessel_id,
                    COUNT(*) AS positions,
                    MIN(timestamp) AS start_time,
                    MAX(timestamp) AS end_time,
                    MIN(latitude) AS min_lat,
                    MAX(latitude) AS max_lat,
                    MIN(longitude) AS min_lon,
                    MAX(longitude) AS max_lon
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                  AND vessel_id = 'SYNTH-003-SRC'
                GROUP BY vessel_id
                """
            ),
            {"scenario_id": scenario_id},
        )

        source = result.fetchone()

        print()
        print("SOURCE VESSEL")
        print("-" * 80)

        if source:
            print(f"Vessel ID          : {source.vessel_id}")
            print(f"Positions           : {source.positions}")
            print(f"Start time          : {source.start_time}")
            print(f"End time            : {source.end_time}")
            print(
                f"Latitude range     : "
                f"{source.min_lat:.6f} -> {source.max_lat:.6f}"
            )
            print(
                f"Longitude range    : "
                f"{source.min_lon:.6f} -> {source.max_lon:.6f}"
            )
        else:
            print("FAIL: Source vessel not found.")

        # ---------------------------------------------------------------
        # Decoys
        # ---------------------------------------------------------------
        result = await db.execute(
            text(
                """
                SELECT
                    vessel_id,
                    COUNT(*) AS positions,
                    MIN(timestamp) AS start_time,
                    MAX(timestamp) AS end_time
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                  AND vessel_id LIKE 'SYNTH-003-DCY%'
                GROUP BY vessel_id
                ORDER BY vessel_id
                """
            ),
            {"scenario_id": scenario_id},
        )

        decoys = result.fetchall()

        print()
        print("DECOY VESSELS")
        print("-" * 80)

        for decoy in decoys:
            print(
                f"{decoy.vessel_id:<20} "
                f"positions={decoy.positions:<5} "
                f"{decoy.start_time} -> {decoy.end_time}"
            )

        # ---------------------------------------------------------------
        # Background vessels
        # ---------------------------------------------------------------
        result = await db.execute(
            text(
                """
                SELECT COUNT(DISTINCT vessel_id)
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                  AND vessel_id LIKE 'SYNTH-003-BG%'
                """
            ),
            {"scenario_id": scenario_id},
        )

        background_count = result.scalar()

        print()
        print("BACKGROUND VESSELS")
        print("-" * 80)
        print(f"Background vessels : {background_count}")

        # ---------------------------------------------------------------
        # Scenario IDs
        # ---------------------------------------------------------------
        result = await db.execute(
            text(
                """
                SELECT
                    COUNT(DISTINCT scenario_id)
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                """
            ),
            {"scenario_id": scenario_id},
        )

        scenario_count = result.scalar()

        print()
        print("SCENARIO ISOLATION")
        print("-" * 80)
        print(f"Distinct scenario IDs in records: {scenario_count}")

        # ---------------------------------------------------------------
        # Source release record
        # ---------------------------------------------------------------
        result = await db.execute(
            text(
                """
                SELECT
                    vessel_id,
                    timestamp,
                    latitude,
                    longitude,
                    speed,
                    course,
                    heading,
                    is_synthetic,
                    scenario_id
                FROM ais_positions
                WHERE scenario_id = :scenario_id
                  AND vessel_id = 'SYNTH-003-SRC'
                  AND timestamp = '2019-07-15 12:00:00+00'
                """
            ),
            {"scenario_id": scenario_id},
        )

        release = result.fetchone()

        print()
        print("SOURCE RELEASE RECORD")
        print("-" * 80)

        if release:
            print(f"Vessel ID    : {release.vessel_id}")
            print(f"Timestamp    : {release.timestamp}")
            print(f"Latitude     : {release.latitude}")
            print(f"Longitude    : {release.longitude}")
            print(f"Speed        : {release.speed}")
            print(f"Course       : {release.course}")
            print(f"Heading      : {release.heading}")
            print(f"Synthetic    : {release.is_synthetic}")
            print(f"Scenario     : {release.scenario_id}")
        else:
            print("FAIL: Release record not found.")

        # ---------------------------------------------------------------
        # Final checks
        # ---------------------------------------------------------------
        print()
        print("=" * 80)
        print("FINAL DATABASE CHECKS")
        print("=" * 80)

        checks = {
            "Position count == 15318": row.positions == 15318,
            "Vessel count == 156": row.vessels == 156,
            "All positions synthetic": row.synthetic_positions == row.positions,
            "Source exists": source is not None,
            "Exactly 5 decoys": len(decoys) == 5,
            "150 background vessels": background_count == 150,
            "Scenario isolated": scenario_count == 1,
            "Release record exists": release is not None,
        }

        all_passed = True

        for name, passed in checks.items():
            status = "PASS" if passed else "FAIL"
            print(f"{name:<35} {status}")

            if not passed:
                all_passed = False

        print()
        print("=" * 80)

        if all_passed:
            print("FINAL RESULT: PASS")
        else:
            print("FINAL RESULT: FAIL")

        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())