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

YEAR = 2019
START_MONTH = 7
END_MONTH = 12

MAX_ALLOWED_SPEED_KNOTS = 40.0


def load_month(path: Path) -> pd.DataFrame:
    """
    Load only the fields required for boundary validation.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Monthly AIS file not found: {path}"
        )

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


def distance_km(
    lat1,
    lon1,
    lat2,
    lon2,
) -> np.ndarray:
    """
    Calculate haversine distance in kilometres.
    """

    lat1 = np.asarray(
        lat1,
        dtype=float,
    )

    lon1 = np.asarray(
        lon1,
        dtype=float,
    )

    lat2 = np.asarray(
        lat2,
        dtype=float,
    )

    lon2 = np.asarray(
        lon2,
        dtype=float,
    )

    dlat = np.radians(
        lat2 - lat1
    )

    dlon = np.radians(
        lon2 - lon1
    )

    lat1_rad = np.radians(
        lat1
    )

    lat2_rad = np.radians(
        lat2
    )

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad)
        * np.cos(lat2_rad)
        * np.sin(dlon / 2.0) ** 2
    )

    # Protect against tiny floating-point overshoots.
    a = np.clip(
        a,
        0.0,
        1.0,
    )

    return (
        2.0
        * 6371.0088
        * np.arcsin(
            np.sqrt(a)
        )
    )


def validate_boundary(
    previous_path: Path,
    current_path: Path,
) -> dict:
    """
    Validate the movement of every common vessel from the last
    observation in the previous month to the first observation
    in the current month.
    """

    previous = load_month(
        previous_path
    )

    current = load_month(
        current_path
    )

    # Last observation of every vessel in previous month.
    previous_last = (
        previous
        .groupby("vessel_id")
        .last()
    )

    # First observation of every vessel in current month.
    current_first = (
        current
        .groupby("vessel_id")
        .first()
    )

    common = (
        previous_last.index
        .intersection(
            current_first.index
        )
    )

    if len(common) == 0:
        raise AssertionError(
            f"No common vessels between "
            f"{previous_path.name} and "
            f"{current_path.name}"
        )

    p = previous_last.loc[common]
    c = current_first.loc[common]

    # ----------------------------------------------------------
    # Time gap
    # ----------------------------------------------------------

    dt_seconds = (
        c["timestamp"]
        - p["timestamp"]
    ).dt.total_seconds()

    if (dt_seconds <= 0).any():
        bad = int(
            (dt_seconds <= 0).sum()
        )

        raise AssertionError(
            f"{bad} non-positive boundary "
            f"time gaps found between "
            f"{previous_path.name} and "
            f"{current_path.name}"
        )

    # ----------------------------------------------------------
    # Spatial displacement
    # ----------------------------------------------------------

    distance = distance_km(
        p["latitude"].to_numpy(),
        p["longitude"].to_numpy(),
        c["latitude"].to_numpy(),
        c["longitude"].to_numpy(),
    )

    # ----------------------------------------------------------
    # Implied speed
    # ----------------------------------------------------------

    speed_knots = (
        distance
        / (
            dt_seconds.to_numpy()
            / 3600.0
        )
        / 1.852
    )

    finite_mask = np.isfinite(
        speed_knots
    )

    if not finite_mask.any():
        raise AssertionError(
            f"No finite boundary speeds "
            f"available for "
            f"{previous_path.name} -> "
            f"{current_path.name}"
        )

    finite_speeds = (
        speed_knots[finite_mask]
    )

    maximum = float(
        np.max(finite_speeds)
    )

    median = float(
        np.median(finite_speeds)
    )

    minimum_gap = float(
        np.min(dt_seconds)
    )

    maximum_gap = float(
        np.max(dt_seconds)
    )

    mean_gap = float(
        np.mean(dt_seconds)
    )

    # ----------------------------------------------------------
    # Speed safety check
    # ----------------------------------------------------------

    if maximum > MAX_ALLOWED_SPEED_KNOTS:
        # Identify the vessel producing the maximum speed.
        max_position = int(
            np.nanargmax(
                np.where(
                    finite_mask,
                    speed_knots,
                    np.nan,
                )
            )
        )

        offending_vessel = (
            str(common[max_position])
        )

        raise AssertionError(
            "\n"
            f"Boundary movement exceeds "
            f"{MAX_ALLOWED_SPEED_KNOTS:.1f} knots.\n"
            f"Transition: "
            f"{previous_path.name} -> "
            f"{current_path.name}\n"
            f"Vessel: {offending_vessel}\n"
            f"Maximum speed: {maximum:.3f} knots"
        )

    return {
        "previous": previous_path.name,
        "current": current_path.name,
        "vessels": len(common),
        "min_gap": minimum_gap,
        "median_gap": float(
            np.median(dt_seconds)
        ),
        "mean_gap": mean_gap,
        "max_gap": maximum_gap,
        "median_speed": median,
        "max_speed": maximum,
    }


def main() -> None:

    print("=" * 80)
    print("FULL-YEAR AIS MONTH-BOUNDARY SPEED VALIDATION")
    print("=" * 80)

    # ----------------------------------------------------------
    # Build all 12 monthly paths.
    # ----------------------------------------------------------

    files = [
        DATA_DIR
        / (
            f"synthetic_ais_"
            f"{YEAR}-"
            f"{month:02d}.csv"
        )
        for month in range(
            START_MONTH,
            END_MONTH + 1,
        )
    ]

    # ----------------------------------------------------------
    # Verify that every monthly file exists.
    # ----------------------------------------------------------

    missing = [
        path
        for path in files
        if not path.exists()
    ]

    if missing:
        print()
        print("Missing monthly files:")

        for path in missing:
            print(
                f"  {path}"
            )

        raise FileNotFoundError(
            f"{len(missing)} monthly AIS files "
            f"are missing."
        )

    print(
        f"Months available: "
        f"{START_MONTH} -> {END_MONTH}"
    )

    print(
        f"Transitions to validate: "
        f"{len(files) - 1}"
    )

    print()

    # ----------------------------------------------------------
    # Validate all 11 boundaries.
    # ----------------------------------------------------------

    results: list[dict] = []

    global_max_speed = 0.0

    for previous_path, current_path in zip(
        files,
        files[1:],
    ):

        result = validate_boundary(
            previous_path,
            current_path,
        )

        results.append(result)

        global_max_speed = max(
            global_max_speed,
            result["max_speed"],
        )

        print(
            f"{result['previous']} -> "
            f"{result['current']}"
        )

        print(
            f"  vessels        : "
            f"{result['vessels']}"
        )

        print(
            f"  min gap (sec)  : "
            f"{result['min_gap']:.1f}"
        )

        print(
            f"  median gap     : "
            f"{result['median_gap']:.1f}"
        )

        print(
            f"  mean gap       : "
            f"{result['mean_gap']:.1f}"
        )

        print(
            f"  max gap (sec)  : "
            f"{result['max_gap']:.1f}"
        )

        print(
            f"  median speed   : "
            f"{result['median_speed']:.3f} kn"
        )

        print(
            f"  max speed      : "
            f"{result['max_speed']:.3f} kn"
        )

        print()

    # ----------------------------------------------------------
    # Final result.
    # ----------------------------------------------------------

    print("=" * 80)
    print("FULL-YEAR BOUNDARY VALIDATION PASSED")
    print("=" * 80)

    print(
        f"Transitions checked : "
        f"{len(results)}"
    )

    print(
        f"Global maximum speed: "
        f"{global_max_speed:.3f} knots"
    )

    print(
        f"Maximum allowed     : "
        f"{MAX_ALLOWED_SPEED_KNOTS:.1f} knots"
    )

    print(
        "All month transitions "
        "are within the allowed speed limit."
    )


if __name__ == "__main__":
    main()