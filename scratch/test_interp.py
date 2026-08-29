import sys
from pathlib import Path
from datetime import datetime, timezone
import xarray as xr
import numpy as np
import time

PROJECT_ROOT = Path("d:/projects/oil-spill-backend")
sys.path.append(str(PROJECT_ROOT))

from app.services.weather_service import WeatherService

def main():
    ws = WeatherService(
        era5_path=PROJECT_ROOT / "data" / "weather" / "raw" / "era5_wind_2019-07-event.nc",
        cmems_path=PROJECT_ROOT / "data" / "ocean" / "raw" / "med_currents_2019-07-event.nc",
    )
    
    # Generate 100 points
    lats = np.linspace(33.0, 34.0, 100)
    lons = np.linspace(33.0, 34.0, 100)
    ts = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    ts_naive = ws._to_naive_utc(ts)
    
    # 1. Scalar approach
    t0 = time.time()
    scalar_wind_u = []
    scalar_wind_v = []
    for lat, lon in zip(lats, lons):
        era5_lon = ws._normalize_longitude(lon, ws.era5[ws.era5_lon].values)
        pt = ws.era5.interp({ws.era5_lat: lat, ws.era5_lon: era5_lon, ws.era5_time: ts_naive}, method="linear")
        scalar_wind_u.append(ws._value(pt[ws.era5_u].values))
        scalar_wind_v.append(ws._value(pt[ws.era5_v].values))
    t1 = time.time()
    print(f"Scalar took: {t1 - t0:.4f}s")
    
    # 2. Xarray Vectorized Dataset
    t2 = time.time()
    lats_da = xr.DataArray(lats, dims="points")
    lons_norm = [ws._normalize_longitude(lon, ws.era5[ws.era5_lon].values) for lon in lons]
    lons_da = xr.DataArray(lons_norm, dims="points")
    
    # Because time is scalar, we can just pass the scalar time, or an array of the same time.
    # Passing scalar time is fine in xarray if it applies to all points.
    pts = ws.era5.interp({ws.era5_lat: lats_da, ws.era5_lon: lons_da, ws.era5_time: ts_naive}, method="linear")
    vec_wind_u = pts[ws.era5_u].values
    vec_wind_v = pts[ws.era5_v].values
    t3 = time.time()
    print(f"Vectorized Dataset took: {t3 - t2:.4f}s")
    
    # Compare
    diff_u = np.abs(np.array(scalar_wind_u) - vec_wind_u)
    diff_v = np.abs(np.array(scalar_wind_v) - vec_wind_v)
    print(f"Max diff U: {np.max(diff_u)}")
    print(f"Max diff V: {np.max(diff_v)}")

    ws.close()

if __name__ == "__main__":
    main()
