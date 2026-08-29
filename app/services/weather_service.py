from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from app.models.drift import EnvironmentalVelocity


class WeatherService:
    """
    Provides historical environmental conditions for the drift model.

    ERA5:
        u10 -> 10 m east-west wind component (m/s)
        v10 -> 10 m north-south wind component (m/s)

    CMEMS:
        uo -> east-west ocean surface current (m/s)
        vo -> north-south ocean surface current (m/s)

    This service is responsible only for reading/interpolating
    environmental data. Oil-drift physics belongs in DriftEngine.
    """

    def __init__(
        self,
        era5_path: str | Path,
        cmems_path: str | Path,
    ) -> None:

        self.era5_path = Path(era5_path)
        self.cmems_path = Path(cmems_path)

        if not self.era5_path.exists():
            raise FileNotFoundError(
                f"ERA5 dataset not found: {self.era5_path}"
            )

        if not self.cmems_path.exists():
            raise FileNotFoundError(
                f"CMEMS dataset not found: {self.cmems_path}"
            )

        self.era5 = xr.open_dataset(
            self.era5_path,
            decode_times=True,
        )

        self.cmems = xr.open_dataset(
            self.cmems_path,
            decode_times=True,
        )

        # Exact structure confirmed from your datasets.
        self.era5_lat = "latitude"
        self.era5_lon = "longitude"
        self.era5_time = "valid_time"

        self.era5_u = "u10"
        self.era5_v = "v10"

        self.cmems_lat = "latitude"
        self.cmems_lon = "longitude"
        self.cmems_time = "time"

        self.cmems_u = "uo"
        self.cmems_v = "vo"

    @staticmethod
    def _to_naive_utc(timestamp: datetime) -> datetime:
        """
        Convert an aware/naive datetime into a naive UTC datetime.

        xarray works particularly cleanly with naive numpy datetime64
        values, while our application can still use UTC-aware datetimes
        at its API boundaries.
        """

        if timestamp.tzinfo is None:
            return timestamp

        return timestamp.astimezone(timezone.utc).replace(
            tzinfo=None
        )

    @staticmethod
    def _value(value) -> float:
        """
        Convert xarray/numpy scalar into a normal Python float.
        """

        return float(np.asarray(value).squeeze())

    def get_velocity(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
    ) -> EnvironmentalVelocity:
        """
        Return linearly interpolated environmental velocity at
        a requested latitude, longitude and UTC timestamp.
        """

        if not -90.0 <= latitude <= 90.0:
            raise ValueError(
                f"Invalid latitude: {latitude}"
            )

        timestamp = self._to_naive_utc(timestamp)

        # ----------------------------------------------------------
        # ERA5 longitude
        # ----------------------------------------------------------
        # Your current dataset uses 30E -> 36E, so the incoming
        # longitude is already compatible. The normalization below
        # also makes the service safer for future datasets.
        era5_longitudes = self.era5[
            self.era5_lon
        ].values

        cmems_longitudes = self.cmems[
            self.cmems_lon
        ].values

        era5_lon = self._normalize_longitude(
            longitude,
            era5_longitudes,
        )

        cmems_lon = self._normalize_longitude(
            longitude,
            cmems_longitudes,
        )

        # ----------------------------------------------------------
        # ERA5 interpolation
        # ----------------------------------------------------------

        era5_point = self.era5.interp(
            {
                self.era5_lat: latitude,
                self.era5_lon: era5_lon,
                self.era5_time: timestamp,
            },
            method="linear",
        )

        # ----------------------------------------------------------
        # CMEMS interpolation
        # ----------------------------------------------------------

        cmems_point = self.cmems.interp(
            {
                self.cmems_lat: latitude,
                self.cmems_lon: cmems_lon,
                self.cmems_time: timestamp,
            },
            method="linear",
        )

        wind_u = self._value(
            era5_point[self.era5_u].values
        )

        wind_v = self._value(
            era5_point[self.era5_v].values
        )

        current_u = self._value(
            cmems_point[self.cmems_u].values
        )

        current_v = self._value(
            cmems_point[self.cmems_v].values
        )

        return EnvironmentalVelocity(
            wind_u=wind_u,
            wind_v=wind_v,
            current_u=current_u,
            current_v=current_v,
        )

    def get_velocities(
        self,
        latitudes: list[float] | np.ndarray,
        longitudes: list[float] | np.ndarray,
        timestamp: datetime,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Return linearly interpolated environmental velocity for multiple
        points at a single UTC timestamp.

        Returns:
            wind_u, wind_v, current_u, current_v (as numpy arrays)
        """
        lats = np.asarray(latitudes, dtype=float)
        lons = np.asarray(longitudes, dtype=float)

        if not np.all((lats >= -90.0) & (lats <= 90.0)):
            raise ValueError("Invalid latitude found in batch.")

        timestamp_naive = self._to_naive_utc(timestamp)

        # ----------------------------------------------------------
        # Normalize longitudes
        # ----------------------------------------------------------
        era5_longitudes = self.era5[self.era5_lon].values
        cmems_longitudes = self.cmems[self.cmems_lon].values

        era5_lons = np.array([
            self._normalize_longitude(lon, era5_longitudes)
            for lon in lons
        ])

        cmems_lons = np.array([
            self._normalize_longitude(lon, cmems_longitudes)
            for lon in lons
        ])

        # ----------------------------------------------------------
        # ERA5 interpolation (Vectorized)
        # ----------------------------------------------------------
        lats_da = xr.DataArray(lats, dims="points")
        era5_lons_da = xr.DataArray(era5_lons, dims="points")

        era5_points = self.era5.interp(
            {
                self.era5_lat: lats_da,
                self.era5_lon: era5_lons_da,
                self.era5_time: timestamp_naive,
            },
            method="linear",
        )

        wind_u = era5_points[self.era5_u].values
        wind_v = era5_points[self.era5_v].values

        # ----------------------------------------------------------
        # CMEMS interpolation (Vectorized)
        # ----------------------------------------------------------
        cmems_lons_da = xr.DataArray(cmems_lons, dims="points")

        cmems_points = self.cmems.interp(
            {
                self.cmems_lat: lats_da,
                self.cmems_lon: cmems_lons_da,
                self.cmems_time: timestamp_naive,
            },
            method="linear",
        )

        current_u = cmems_points[self.cmems_u].values
        current_v = cmems_points[self.cmems_v].values

        return wind_u, wind_v, current_u, current_v

    @staticmethod
    def _normalize_longitude(
        longitude: float,
        dataset_longitudes: np.ndarray,
    ) -> float:
        """
        Match the longitude convention used by the dataset.

        Handles:
            -180 ... 180
        and:
            0 ... 360
        """

        lon_min = float(np.min(dataset_longitudes))
        lon_max = float(np.max(dataset_longitudes))

        # Dataset uses 0..360 convention.
        if lon_min >= 0.0 and lon_max > 180.0:
            return longitude % 360.0

        # Dataset uses -180..180 convention.
        return ((longitude + 180.0) % 360.0) - 180.0

    def describe(self) -> dict:
        """
        Return dataset information useful for debugging.
        """

        return {
            "era5_dimensions": dict(self.era5.sizes),
            "era5_coordinates": list(self.era5.coords),
            "era5_variables": list(self.era5.data_vars),
            "cmems_dimensions": dict(self.cmems.sizes),
            "cmems_coordinates": list(self.cmems.coords),
            "cmems_variables": list(self.cmems.data_vars),
        }

    def close(self) -> None:
        """Close both NetCDF datasets."""

        self.era5.close()
        self.cmems.close()

    def __enter__(self) -> "WeatherService":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()