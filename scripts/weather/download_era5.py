import os
from pathlib import Path

import cdsapi
from dotenv import load_dotenv


load_dotenv()

OUTPUT = Path("data/weather/raw/era5_wind_2019-07-event.nc")

client = cdsapi.Client(
    url=os.getenv("CDSAPI_URL"),
    key=os.getenv("CDSAPI_KEY"),
)

request = {
    "product_type": ["reanalysis"],
    "variable": [
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
    ],
    "year": ["2019"],
    "month": ["07"],
    "day": [
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
    ],
    "time": [
        "00:00",
        "01:00",
        "02:00",
        "03:00",
        "04:00",
        "05:00",
        "06:00",
        "07:00",
        "08:00",
        "09:00",
        "10:00",
        "11:00",
        "12:00",
        "13:00",
        "14:00",
        "15:00",
        "16:00",
        "17:00",
        "18:00",
        "19:00",
        "20:00",
        "21:00",
        "22:00",
        "23:00",
    ],
    "data_format": "netcdf",
    "download_format": "unarchived",
    "area": [37, 30, 30, 36],
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

print("Downloading ERA5 wind data...")
print(f"Output: {OUTPUT}")

client.retrieve(
    "reanalysis-era5-single-levels",
    request,
).download(str(OUTPUT))

print("ERA5 download complete.")