from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "ais"
    / "processed"
    / "yearly"
)


def load_month(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        usecols=[
            "vessel_id",
            "timestamp",
            "latitude",
            "longitude",
        ],
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    return df.sort_values(
        ["vessel_id", "timestamp"]
    )


def main() -> None:
    files = sorted(
        DATA_DIR.glob(
            "synthetic_ais_2019-0*.csv"
        )
    )

    print("=" * 80)
    print("AIS MONTH CONTINUITY VALIDATION")
    print("=" * 80)

    print(
        f"Files found: {len(files)}"
    )

    if len(files) != 6:
        raise RuntimeError(
            "Expected January-June "
            "(6 files)."
        )

    fleet_ids: set[str] | None = None

    previous_last: pd.DataFrame | None = None
    previous_name: str | None = None

    for path in files:
        df = load_month(path)

        current_ids = set(
            df["vessel_id"].unique()
        )

        print()
        print(path.name)
        print(
            f"  records : {len(df):,}"
        )
        print(
            f"  vessels : {len(current_ids)}"
        )
        print(
            f"  range   : "
            f"{df.timestamp.min()} -> "
            f"{df.timestamp.max()}"
        )

        if fleet_ids is None:
            fleet_ids = current_ids
        else:
            same_fleet = (
                current_ids == fleet_ids
            )

            print(
                f"  same fleet as January: "
                f"{same_fleet}"
            )

            if not same_fleet:
                raise AssertionError(
                    "Vessel fleet changed "
                    f"in {path.name}"
                )

        # Last observation for each vessel.
        last = (
            df.sort_values(
                ["vessel_id", "timestamp"]
            )
            .groupby("vessel_id")
            .last()
        )

        # First observation for each vessel.
        first = (
            df.sort_values(
                ["vessel_id", "timestamp"]
            )
            .groupby("vessel_id")
            .first()
        )

        if previous_last is not None:
            common = (
                previous_last.index
                .intersection(first.index)
            )

            dlat = (
                first.loc[
                    common,
                    "latitude",
                ]
                - previous_last.loc[
                    common,
                    "latitude",
                ]
            ).abs()

            dlon = (
                first.loc[
                    common,
                    "longitude",
                ]
                - previous_last.loc[
                    common,
                    "longitude",
                ]
            ).abs()

            print(
                f"  continuity from "
                f"{previous_name}:"
            )

            print(
                f"    common vessels : "
                f"{len(common)}"
            )

            print(
                f"    max lat delta  : "
                f"{dlat.max():.6f}"
            )

            print(
                f"    max lon delta  : "
                f"{dlon.max():.6f}"
            )

        previous_last = last
        previous_name = path.name

    print()
    print("=" * 80)
    print("CONTINUITY VALIDATION COMPLETE")
    print("=" * 80)

    print(
        f"Persistent fleet: "
        f"{len(fleet_ids or [])} vessels"
    )


if __name__ == "__main__":
    main()