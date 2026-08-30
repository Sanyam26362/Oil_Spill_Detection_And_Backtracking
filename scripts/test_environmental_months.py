from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app.services.weather_service import WeatherService


# Months to verify across the 2019 environmental dataset.
MONTHS_TO_TEST = [1, 3, 6, 7, 9, 12]

# Point inside the downloaded ERA5/CMEMS spatial domain.
TEST_LATITUDE = 34.0
TEST_LONGITUDE = 33.0


async def run_month_test(
    month: int,
    weather_service: WeatherService,
) -> None:
    """
    Validate real ERA5 + CMEMS lookup for one month.

    Checks:
    1. Scalar lookup succeeds.
    2. Vectorized lookup succeeds.
    3. Scalar and vectorized results agree numerically.
    """

    timestamp = datetime(
        2019,
        month,
        15,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    try:
        # ==========================================================
        # SCALAR LOOKUP
        # ==========================================================

        velocity = weather_service.get_velocity(
            TEST_LATITUDE,
            TEST_LONGITUDE,
            timestamp,
        )

        u10 = velocity.wind_u
        v10 = velocity.wind_v
        uo = velocity.current_u
        vo = velocity.current_v

        # ==========================================================
        # VECTORIZED LOOKUP
        # ==========================================================

        (
            u10_vector,
            v10_vector,
            uo_vector,
            vo_vector,
        ) = weather_service.get_velocities(
            np.array([TEST_LATITUDE]),
            np.array([TEST_LONGITUDE]),
            timestamp,
        )

        # ==========================================================
        # EXTRACT FIRST VECTOR RESULT
        # ==========================================================

        u10_v = float(u10_vector[0])
        v10_v = float(v10_vector[0])
        uo_v = float(uo_vector[0])
        vo_v = float(vo_vector[0])

        # ==========================================================
        # NUMERICAL EQUIVALENCE
        # ==========================================================

        scalar_values = np.array(
            [
                u10,
                v10,
                uo,
                vo,
            ],
            dtype=float,
        )

        vector_values = np.array(
            [
                u10_v,
                v10_v,
                uo_v,
                vo_v,
            ],
            dtype=float,
        )

        difference = np.abs(
            scalar_values - vector_values
        )

        max_difference = float(
            np.nanmax(difference)
        )

        if not np.allclose(
            scalar_values,
            vector_values,
            rtol=1e-6,
            atol=1e-8,
            equal_nan=True,
        ):
            raise AssertionError(
                "Scalar/vectorized environmental "
                f"lookup mismatch. "
                f"Maximum difference: "
                f"{max_difference:.6e}"
            )

        # ==========================================================
        # SPEEDS
        # ==========================================================

        wind_speed = float(
            np.hypot(
                u10,
                v10,
            )
        )

        current_speed = float(
            np.hypot(
                uo,
                vo,
            )
        )

        # ==========================================================
        # OUTPUT
        # ==========================================================

        print(
            f"Month {month:02d} SUCCESS | "
            f"time={timestamp.isoformat()} | "
            f"wind=({u10:.4f}, {v10:.4f}) m/s | "
            f"wind_speed={wind_speed:.4f} m/s | "
            f"current=({uo:.4f}, {vo:.4f}) m/s | "
            f"current_speed={current_speed:.4f} m/s | "
            f"max scalar/vector diff={max_difference:.3e}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"Month {month:02d} FAILED | "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        raise


async def main() -> None:
    print("=" * 80)
    print(
        "REAL YEAR-WIDE ENVIRONMENTAL FORCING TEST"
    )
    print("=" * 80)

    print(
        "Testing real ERA5 wind + CMEMS surface currents"
    )

    print(
        f"Location : "
        f"{TEST_LATITUDE:.2f} N, "
        f"{TEST_LONGITUDE:.2f} E"
    )

    print(
        "Months   : "
        + ", ".join(
            f"{month:02d}"
            for month in MONTHS_TO_TEST
        )
    )

    print()

    # ==========================================================
    # YEAR-AWARE WEATHER SERVICE
    # ==========================================================

    weather_service = WeatherService(
        weather_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "weather"
            / "raw"
            / "yearly"
        ),
        ocean_yearly_dir=(
            PROJECT_ROOT
            / "data"
            / "ocean"
            / "raw"
            / "yearly"
        ),
    )

    try:
        for month in MONTHS_TO_TEST:
            await run_month_test(
                month,
                weather_service,
            )

    finally:
        weather_service.close()

    print()
    print("=" * 80)
    print(
        "YEAR-WIDE ENVIRONMENTAL TEST PASSED"
    )
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())