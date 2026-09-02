import xarray as xr
from pathlib import Path

spill_lat = (35.0, 35.1)
spill_lon = (24.0, 24.1)

checks = [
    (
        "ERA5",
        Path("data/weather/raw/yearly"),
        "era5_wind_2019-{month:02d}.nc",
        "valid_time",
        ("u10", "v10"),
    ),
    (
        "CMEMS",
        Path("data/ocean/raw/yearly"),
        "med_currents_2019-{month:02d}.nc",
        "time",
        ("uo", "vo"),
    ),
]

print()
print("=" * 110)
print("2019 FEB-DEC ENVIRONMENTAL DATA VALIDATION")
print("=" * 110)

all_ok = True

for month in range(2, 13):

    for dataset, root, pattern, time_coord, variables in checks:

        path = root / pattern.format(month=month)

        print()
        print(f"{dataset} 2019-{month:02d}")
        print("-" * 60)

        if not path.exists():
            print("STATUS: FAIL - FILE MISSING")
            all_ok = False
            continue

        try:
            ds = xr.open_dataset(path)

            lat_min = float(ds.latitude.min())
            lat_max = float(ds.latitude.max())
            lon_min = float(ds.longitude.min())
            lon_max = float(ds.longitude.max())

            first_time = ds[time_coord].values[0]
            last_time = ds[time_coord].values[-1]

            variables_ok = all(
                variable in ds.data_vars
                for variable in variables
            )

            spatial_ok = (
                lat_min <= spill_lat[0]
                and lat_max >= spill_lat[1]
                and lon_min <= spill_lon[0]
                and lon_max >= spill_lon[1]
            )

            status = variables_ok and spatial_ok

            print(f"File       : {path.name}")
            print(f"Dimensions : {dict(ds.sizes)}")
            print(f"Latitude   : {lat_min} -> {lat_max}")
            print(f"Longitude  : {lon_min} -> {lon_max}")
            print(f"Time       : {first_time} -> {last_time}")
            print(f"Variables  : {list(ds.data_vars)}")
            print(f"Spatial OK : {spatial_ok}")
            print(f"Variables OK: {variables_ok}")
            print(f"STATUS     : {'PASS' if status else 'FAIL'}")

            if not status:
                all_ok = False

            ds.close()

        except Exception as exc:
            print(f"STATUS: FAIL - {exc}")
            all_ok = False

print()
print("=" * 110)
print(f"OVERALL: {'PASS - FEB-DEC DATA LOOKS CORRECT' if all_ok else 'FAIL - SOME FILES NEED ATTENTION'}")
print("=" * 110)
