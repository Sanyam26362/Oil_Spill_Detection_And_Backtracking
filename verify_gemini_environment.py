import xarray as xr
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from app.services.weather_service import WeatherService

print("=" * 100)
print("INDEPENDENT ENVIRONMENTAL DATA VERIFICATION")
print("=" * 100)

WEATHER = Path("data/weather/raw/yearly")
OCEAN = Path("data/ocean/raw/yearly")

# Your actual operational region
LAT_MIN, LAT_MAX = 34.5, 35.5
LON_MIN, LON_MAX = 23.5, 24.5

all_ok = True

def check_file(path, time_var, variables, expected_year, expected_month):
    global all_ok

    print("\n" + "-" * 100)
    print(path.name)

    if not path.exists():
        print("? FILE MISSING")
        all_ok = False
        return

    try:
        ds = xr.open_dataset(path, engine="h5netcdf")

        print("Dimensions:", dict(ds.sizes))
        print("Variables :", list(ds.data_vars))

        # Variables
        vars_ok = all(v in ds.data_vars for v in variables)
        print("Variables OK:", vars_ok)

        # Spatial coverage
        lat_min = float(ds.latitude.min())
        lat_max = float(ds.latitude.max())
        lon_min = float(ds.longitude.min())
        lon_max = float(ds.longitude.max())

        spatial_ok = (
            lat_min <= LAT_MIN
            and lat_max >= LAT_MAX
            and lon_min <= LON_MIN
            and lon_max >= LON_MAX
        )

        print(f"Latitude : {lat_min} -> {lat_max}")
        print(f"Longitude: {lon_min} -> {lon_max}")
        print("Spatial coverage OK:", spatial_ok)

        # Time
        times = ds[time_var].values
        first = times[0]
        last = times[-1]

        print("Time:", first, "->", last)

        # Expected month
        expected_start = np.datetime64(
            f"{expected_year:04d}-{expected_month:02d}-01T00:00:00"
        )

        if expected_month == 12:
            expected_end = np.datetime64(
                f"{expected_year + 1:04d}-01-01T00:00:00"
            )
        else:
            expected_end = np.datetime64(
                f"{expected_year:04d}-{expected_month + 1:02d}-01T00:00:00"
            )

        # ERA5 ends at final hour of month.
        # CMEMS intentionally contains the first timestamp of next month.
        if time_var == "valid_time":
            time_ok = (
                np.datetime64(first) == expected_start
                and np.datetime64(last) < expected_end
            )
        else:
            time_ok = (
                np.datetime64(first) == expected_start
                and np.datetime64(last) == expected_end
            )

        print("Time coverage OK:", time_ok)

        # NaN statistics
        for var in variables:
            arr = ds[var].values
            nan_pct = float(np.isnan(arr).mean() * 100)
            finite_pct = float(np.isfinite(arr).mean() * 100)

            print(
                f"{var}: NaN={nan_pct:.2f}% | "
                f"Finite={finite_pct:.2f}%"
            )

        # Basic data sanity
        data_ok = True

        for var in variables:
            arr = ds[var].values
            finite = arr[np.isfinite(arr)]

            if finite.size == 0:
                data_ok = False
                print(f"? {var}: NO FINITE DATA")
                continue

            print(
                f"{var}: min={finite.min():.6f}, "
                f"max={finite.max():.6f}, "
                f"mean={finite.mean():.6f}"
            )

        status = vars_ok and spatial_ok and time_ok and data_ok

        print("STATUS:", "? PASS" if status else "? FAIL")

        if not status:
            all_ok = False

        ds.close()

    except Exception as e:
        print("? ERROR:", repr(e))
        all_ok = False


# ------------------------------------------------------------------
# 2018-12 + 2019-01..12
# ------------------------------------------------------------------

print("\nChecking ERA5...")
check_file(
    WEATHER / "era5_wind_2018-12.nc",
    "valid_time",
    ("u10", "v10"),
    2018,
    12
)

for month in range(1, 13):
    check_file(
        WEATHER / f"era5_wind_2019-{month:02d}.nc",
        "valid_time",
        ("u10", "v10"),
        2019,
        month
    )

print("\nChecking CMEMS...")
check_file(
    OCEAN / "med_currents_2018-12.nc",
    "time",
    ("uo", "vo"),
    2018,
    12
)

for month in range(1, 13):
    check_file(
        OCEAN / f"med_currents_2019-{month:02d}.nc",
        "time",
        ("uo", "vo"),
        2019,
        month
    )


# ------------------------------------------------------------------
# WeatherService lookup verification
# ------------------------------------------------------------------

print("\n" + "=" * 100)
print("WEATHER SERVICE LOOKUP TEST")
print("=" * 100)

test_points = [
    (35.0481, 24.0379, datetime(2019, 1, 1, 3, 42, 35, tzinfo=timezone.utc)),
    (35.0500, 24.0500, datetime(2019, 2, 15, 12, 30, 0, tzinfo=timezone.utc)),
    (35.0700, 24.0700, datetime(2019, 6, 10, 18, 15, 0, tzinfo=timezone.utc)),
    (35.0300, 24.0300, datetime(2019, 10, 20, 6, 45, 0, tzinfo=timezone.utc)),
    (35.0800, 24.0800, datetime(2019, 12, 15, 20, 10, 0, tzinfo=timezone.utc)),
    # Critical cross-year case
    (35.0481, 24.0379, datetime(2018, 12, 31, 12, 0, 35, tzinfo=timezone.utc)),
]

try:
    service = WeatherService(
        weather_yearly_dir="data/weather/raw/yearly",
        ocean_yearly_dir="data/ocean/raw/yearly"
    )

    for lat, lon, timestamp in test_points:
        print("\nTest:")
        print("Location:", lat, lon)
        print("Time    :", timestamp)

        result = service.get_velocity(
            latitude=lat,
            longitude=lon,
            timestamp=timestamp
        )

        values = [
            result.wind_u,
            result.wind_v,
            result.current_u,
            result.current_v,
        ]

        finite = all(np.isfinite(values))

        print("Result  :", result)
        print("Finite  :", finite)

        if not finite:
            print("? LOOKUP FAILED")
            all_ok = False
        else:
            print("? LOOKUP PASS")

    service.close()

except Exception as e:
    print("? WeatherService ERROR:", repr(e))
    all_ok = False


# ------------------------------------------------------------------
# Final result
# ------------------------------------------------------------------

print("\n" + "=" * 100)

if all_ok:
    print("? INDEPENDENT VERIFICATION PASSED")
    print("Environmental data appears structurally valid and WeatherService")
    print("successfully returns finite wind/current values.")
else:
    print("? INDEPENDENT VERIFICATION FAILED")
    print("One or more checks require investigation.")

print("=" * 100)
