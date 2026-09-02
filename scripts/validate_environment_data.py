import xarray as xr
from pathlib import Path
import numpy as np

def validate_datasets():
    era5_dir = Path("data/weather/raw/yearly")
    cmems_dir = Path("data/ocean/raw/yearly")

    print("========================================")
    print("ENVIRONMENTAL DATA VALIDATION")
    print("========================================\n")

    # Target region bounds
    target_N = 35.1
    target_S = 35.0
    target_E = 24.1
    target_W = 24.0

    print(f"Target Region: Lat {target_S} to {target_N}, Lon {target_W} to {target_E}\n")

    months_to_check = [("2018", "12")] + [("2019", f"{m:02d}") for m in range(1, 13)]

    status = []

    for year, month in months_to_check:
        print(f"--- {year}-{month} ---")

        era5_file = era5_dir / f"era5_wind_{year}-{month}.nc"
        cmems_file = cmems_dir / f"med_currents_{year}-{month}.nc"

        month_pass = True

        # Validate ERA5
        print(f"ERA5 File: {era5_file.name}")
        if not era5_file.exists():
            print("  [FAIL] ERA5 file does not exist.")
            month_pass = False
        else:
            try:
                ds = xr.open_dataset(era5_file)
                # Check vars
                if 'u10' not in ds or 'v10' not in ds:
                    print("  [FAIL] Missing u10 or v10")
                    month_pass = False

                # Check coords
                if 'latitude' not in ds.coords or 'longitude' not in ds.coords:
                    print("  [FAIL] Missing lat/lon coords")
                    month_pass = False

                time_var = 'valid_time' if 'valid_time' in ds.coords or 'valid_time' in ds.dims else 'time'
                if time_var not in ds.coords and time_var not in ds.dims:
                    print("  [FAIL] Missing time coord")
                    month_pass = False
                else:
                    times = ds[time_var].values
                    print(f"  Time: {len(times)} records, {times[0]} to {times[-1]}")

                lat = ds['latitude'].values
                lon = ds['longitude'].values
                print(f"  Grid: {len(lat)} lats, {len(lon)} lons")

                # Normalize lon for ERA5 check
                lon_min = lon.min()
                lon_max = lon.max()

                # Convert 0..360 to -180..180 if needed for comparison
                if lon_max > 180 and target_E < 180:
                    lon_min_norm = (lon_min + 180) % 360 - 180
                    lon_max_norm = (lon_max + 180) % 360 - 180
                else:
                    lon_min_norm, lon_max_norm = lon_min, lon_max

                print(f"  Coverage: Lat {lat.min():.2f} to {lat.max():.2f}, Lon {lon_min:.2f} to {lon_max:.2f}")

                if not (lat.min() <= target_S and lat.max() >= target_N):
                    print("  [FAIL] Latitude coverage is insufficient.")
                    month_pass = False
                if not (lon_min_norm <= target_W and lon_max_norm >= target_E):
                    print(f"  [FAIL] Longitude coverage is insufficient. Need {target_W}-{target_E}, got {lon_min_norm}-{lon_max_norm}")
                    month_pass = False

                u = ds['u10'].values
                nans = np.isnan(u).sum()
                nan_pct = (nans / u.size) * 100
                print(f"  NaNs: {nans}/{u.size} ({nan_pct:.2f}%)")

                ds.close()
            except Exception as e:
                print(f"  [FAIL] Error reading ERA5: {e}")
                month_pass = False

        # Validate CMEMS
        print(f"CMEMS File: {cmems_file.name}")
        if not cmems_file.exists():
            print("  [FAIL] CMEMS file does not exist.")
            month_pass = False
        else:
            try:
                ds = xr.open_dataset(cmems_file)
                if 'uo' not in ds or 'vo' not in ds:
                    print("  [FAIL] Missing uo or vo")
                    month_pass = False

                if 'latitude' not in ds.coords or 'longitude' not in ds.coords or 'time' not in ds.coords:
                    print("  [FAIL] Missing coords")
                    month_pass = False
                else:
                    times = ds['time'].values
                    print(f"  Time: {len(times)} records, {times[0]} to {times[-1]}")

                lat = ds['latitude'].values
                lon = ds['longitude'].values
                print(f"  Grid: {len(lat)} lats, {len(lon)} lons")
                print(f"  Coverage: Lat {lat.min():.2f} to {lat.max():.2f}, Lon {lon.min():.2f} to {lon.max():.2f}")

                if not (lat.min() <= target_S and lat.max() >= target_N):
                    print("  [FAIL] Latitude coverage is insufficient.")
                    month_pass = False
                if not (lon.min() <= target_W and lon.max() >= target_E):
                    print("  [FAIL] Longitude coverage is insufficient.")
                    month_pass = False

                u = ds['uo'].values
                nans = np.isnan(u).sum()
                nan_pct = (nans / u.size) * 100
                print(f"  NaNs: {nans}/{u.size} ({nan_pct:.2f}%)")

                ds.close()
            except Exception as e:
                print(f"  [FAIL] Error reading CMEMS: {e}")
                month_pass = False

        print(f"  MONTH STATUS: {'PASS' if month_pass else 'FAIL'}\n")
        status.append((f"{year}-{month}", month_pass))

    print("========================================")
    print("SUMMARY")
    for s in status:
        print(f"{s[0]}: {'PASS' if s[1] else 'FAIL'}")

if __name__ == "__main__":
    validate_datasets()
