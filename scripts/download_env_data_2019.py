import os
from pathlib import Path
import cdsapi
import calendar
import subprocess
from dotenv import load_dotenv

load_dotenv()

ERA5_DIR = Path("data/weather/raw/yearly")
CMEMS_DIR = Path("data/ocean/raw/yearly")

ERA5_DIR.mkdir(parents=True, exist_ok=True)
CMEMS_DIR.mkdir(parents=True, exist_ok=True)

# Bounding box
N, W, S, E = 35.5, 23.5, 34.5, 24.5

# ERA5 bounding box: North, West, South, East
ERA5_AREA = [N, W, S, E]

def download_era5(year, month):
    client = cdsapi.Client(
        url=os.getenv("CDSAPI_URL"),
        key=os.getenv("CDSAPI_KEY"),
    )

    _, last_day = calendar.monthrange(year, month)
    days = [f"{d:02d}" for d in range(1, last_day + 1)]
    times = [f"{h:02d}:00" for h in range(24)]

    filename = f"era5_wind_{year}-{month:02d}.nc"
    output_path = ERA5_DIR / filename

    if output_path.exists():
        print(f"Skipping ERA5 {filename}, already exists.")
        return

    request = {
        "product_type": ["reanalysis"],
        "variable": [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
        ],
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": days,
        "time": times,
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": ERA5_AREA,
    }

    print(f"Downloading ERA5 {year}-{month:02d}...")
    client.retrieve(
        "reanalysis-era5-single-levels",
        request,
    ).download(str(output_path))
    print(f"Finished {filename}")

def download_cmems(year, month):
    filename = f"med_currents_{year}-{month:02d}.nc"
    output_path = CMEMS_DIR / filename

    if output_path.exists():
        print(f"Skipping CMEMS {filename}, already exists.")
        return

    _, last_day = calendar.monthrange(year, month)

    start_time = f"{year}-{month:02d}-01 00:00:00"
    end_time = f"{year}-{month:02d}-{last_day:02d} 23:59:59"

    print(f"Downloading CMEMS {year}-{month:02d}...")

    import sys
    cm_exe = sys.executable.replace("python.exe", "copernicusmarine.exe")
    cmd = [
        cm_exe, "subset",
        "-i", "cmems_mod_med_phy-cur_my_4.2km_PT1H-m",
        "-x", str(W), "-X", str(E),
        "-y", str(S), "-Y", str(N),
        "-t", start_time, "-T", end_time,
        "-v", "uo", "-v", "vo",
        "-o", str(CMEMS_DIR),
        "-f", filename,
        "--force-download"
    ]

    # We use copernicusmarine CLI. Ensure it's authenticated.
    # Note: copernicusmarine needs credentials, usually in .copernicusmarine-credentials, or via env vars.
    # We will assume CLI is configured or relies on COPERNICUSMARINE_COP_USER / COPERNICUSMARINE_COP_PWD
    subprocess.run(cmd, check=True)
    print(f"Finished {filename}")

if __name__ == "__main__":
    # Special 2018-12 case
    download_era5(2018, 12)
    download_cmems(2018, 12)

    # 2019
    for m in range(1, 13):
        download_era5(2019, m)
        download_cmems(2019, m)
