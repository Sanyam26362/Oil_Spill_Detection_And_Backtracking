from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
import threading

import numpy as np
import xarray as xr

from app.models.drift import EnvironmentalVelocity

class WeatherService:
    """
    Provides historical environmental conditions for the drift model.
    Supports:

    1. Existing single-pair datasets:
        era5_wind_2019-07-event.nc
        med_currents_2019-07-event.nc

    2. Yearly monthly datasets:
        data/weather/raw/yearly/era5_wind_2019-01.nc
        data/ocean/raw/yearly/med_currents_2019-01.nc

    Yearly mode normally keeps one month cached.

    Special handling is included for timestamps near a month boundary:
    if interpolation requires the first timestamp of the next month,
    the next month's dataset is loaded temporarily.

    ERA5:
        u10 -> 10 m east-west wind component (m/s)
        v10 -> 10 m north-south wind component (m/s)

    CMEMS:
        uo -> east-west ocean surface current (m/s)
        vo -> north-south ocean surface current (m/s)
    """

    def __init__(
        self,
        era5_path: str | Path | None = None,
        cmems_path: str | Path | None = None,
        weather_yearly_dir: str | Path | None = None,
        ocean_yearly_dir: str | Path | None = None,
        cache_max_months: int = 3,
    ) -> None:

        # ----------------------------------------------------------
        # Operating modes
        # ----------------------------------------------------------

        self._single_dataset_mode = (
            era5_path is not None
            and cmems_path is not None
        )

        self._yearly_mode = (
            weather_yearly_dir is not None
            or ocean_yearly_dir is not None
        )

        if not self._single_dataset_mode and not self._yearly_mode:
            raise ValueError(
                "Provide either era5_path + cmems_path "
                "or weather_yearly_dir + ocean_yearly_dir."
            )

        if self._single_dataset_mode and self._yearly_mode:
            raise ValueError(
                "Do not mix single-dataset mode and yearly mode."
            )

        # ----------------------------------------------------------
        # Paths
        # ----------------------------------------------------------

        self.era5_path = (
            Path(era5_path)
            if era5_path is not None
            else None
        )

        self.cmems_path = (
            Path(cmems_path)
            if cmems_path is not None
            else None
        )

        self.weather_yearly_dir = (
            Path(weather_yearly_dir)
            if weather_yearly_dir is not None
            else None
        )

        self.ocean_yearly_dir = (
            Path(ocean_yearly_dir)
            if ocean_yearly_dir is not None
            else None
        )

        # ----------------------------------------------------------
        # Validate single-dataset mode
        # ----------------------------------------------------------

        if self._single_dataset_mode:

            assert self.era5_path is not None
            assert self.cmems_path is not None

            if not self.era5_path.exists():
                raise FileNotFoundError(
                    f"ERA5 dataset not found: {self.era5_path}"
                )

            if not self.cmems_path.exists():
                raise FileNotFoundError(
                    f"CMEMS dataset not found: {self.cmems_path}"
                )

        # ----------------------------------------------------------
        # Validate yearly mode
        # ----------------------------------------------------------

        if self._yearly_mode:

            if (
                self.weather_yearly_dir is None
                or self.ocean_yearly_dir is None
            ):
                raise ValueError(
                    "Both weather_yearly_dir and "
                    "ocean_yearly_dir are required in yearly mode."
                )

            if not self.weather_yearly_dir.exists():
                raise FileNotFoundError(
                    "Yearly ERA5 directory not found: "
                    f"{self.weather_yearly_dir}"
                )

            if not self.ocean_yearly_dir.exists():
                raise FileNotFoundError(
                    "Yearly CMEMS directory not found: "
                    f"{self.ocean_yearly_dir}"
                )

        # ----------------------------------------------------------
        # Currently loaded datasets
        # ----------------------------------------------------------

        self.era5: xr.Dataset | None = None
        self.cmems: xr.Dataset | None = None

        self._loaded_year: int | None = None
        self._loaded_month: int | None = None

        # C1: Multi-month LRU cache (holding up to cache_max_months (era5, cmems) pairs).
        self.cache_max_months: int = max(1, cache_max_months)
        self._month_cache: OrderedDict[tuple[int, int], tuple[xr.Dataset, xr.Dataset]] = OrderedDict()

        # E1: Cache concatenated cross-month dataset pairs keyed by (year, month).
        self._cross_month_cache: dict[tuple[int, int], tuple[xr.Dataset, xr.Dataset]] = {}

        # D1: RLock for thread-safety when get_spill_visualization runs
        # in FastAPI's threadpool with a shared module-level instance.
        self._lock = threading.RLock()

        # E3: Cache dataset longitude bounds to avoid np.min/max on every
        # velocity query. Invalidated whenever a new dataset is loaded.
        self._era5_lon_min: float | None = None
        self._era5_lon_max: float | None = None
        self._cmems_lon_min: float | None = None
        self._cmems_lon_max: float | None = None

        # ----------------------------------------------------------
        # Coordinate / variable names
        # ----------------------------------------------------------

        self.era5_lat = "latitude"
        self.era5_lon = "longitude"
        self.era5_time = "time"

        self.era5_u = "u10"
        self.era5_v = "v10"

        self.cmems_lat = "latitude"
        self.cmems_lon = "longitude"
        self.cmems_time = "time"

        self.cmems_u = "uo"
        self.cmems_v = "vo"

        # ----------------------------------------------------------
        # Single dataset initialization
        # ----------------------------------------------------------

        if self._single_dataset_mode:
            self._load_single_datasets()

    # ==============================================================
    # DATASET LOADING
    # ==============================================================

    def _load_single_datasets(self) -> None:
        """Load explicitly supplied ERA5/CMEMS datasets."""

        assert self.era5_path is not None
        assert self.cmems_path is not None

        era5 = xr.open_dataset(
            self.era5_path,
            decode_times=True,
            cache=False,
            engine="netcdf4",
        )

        cmems = xr.open_dataset(
            self.cmems_path,
            decode_times=True,
            cache=False,
            engine="netcdf4",
        )

        self.era5 = self._prepare_era5(era5)
        self.cmems = self._prepare_cmems(cmems)

    def _prepare_era5(
        self,
        dataset: xr.Dataset,
    ) -> xr.Dataset:
        """
        Normalize ERA5 time coordinate.

        New ERA5 files use:
            valid_time

        Internally the service uses:
            time
        """

        raw_close = dataset._close

        if "valid_time" in dataset.coords:
            dataset = dataset.rename(
                {"valid_time": "time"}
            )

        elif "valid_time" in dataset.dims:
            dataset = dataset.rename(
                {"valid_time": "time"}
            )

        if raw_close is not None:
            dataset.set_close(raw_close)

        if "time" not in dataset.coords:
            dataset.close()

            raise ValueError(
                "ERA5 dataset does not contain "
                "a usable time coordinate."
            )

        required = {
            self.era5_lat,
            self.era5_lon,
            self.era5_u,
            self.era5_v,
        }

        missing = [
            name
            for name in required
            if name not in dataset
            and name not in dataset.coords
        ]

        if missing:
            dataset.close()

            raise ValueError(
                "ERA5 dataset missing required "
                f"fields: {missing}"
            )

        dataset.load()
        return dataset

    def _prepare_cmems(
        self,
        dataset: xr.Dataset,
    ) -> xr.Dataset:
        """Validate CMEMS dataset structure."""

        if "time" not in dataset.coords:
            dataset.close()

            raise ValueError(
                "CMEMS dataset does not contain "
                "a usable time coordinate."
            )

        required = {
            self.cmems_lat,
            self.cmems_lon,
            self.cmems_u,
            self.cmems_v,
        }

        missing = [
            name
            for name in required
            if name not in dataset
            and name not in dataset.coords
        ]

        if missing:
            dataset.close()

            raise ValueError(
                "CMEMS dataset missing required "
                f"fields: {missing}"
            )

        dataset.load()
        return dataset

    def _set_active_month(
        self,
        year: int,
        month: int,
    ) -> None:
        """
        Set the active month datasets and update loaded coordinates / bounds.
        The active month is always the month of the most recently requested timestamp.
        """
        if (year, month) in self._month_cache:
            self._month_cache.move_to_end((year, month))
            era5, cmems = self._month_cache[(year, month)]
            self.era5 = era5
            self.cmems = cmems
            self._loaded_year = year
            self._loaded_month = month

            _e5_lons = era5[self.era5_lon].values
            self._era5_lon_min = float(np.min(_e5_lons))
            self._era5_lon_max = float(np.max(_e5_lons))
            _cm_lons = cmems[self.cmems_lon].values
            self._cmems_lon_min = float(np.min(_cm_lons))
            self._cmems_lon_max = float(np.max(_cm_lons))

    def _evict_lru_month(self) -> None:
        """Evict the least-recently-used month from the cache."""
        evicted_ym, (evicted_era5, evicted_cmems) = self._month_cache.popitem(last=False)
        try:
            evicted_era5.close()
        except Exception:
            pass
        try:
            evicted_cmems.close()
        except Exception:
            pass

        # E1: Invalidate any cross-month concatenated pairs using this month
        keys_to_remove = []
        for key in list(self._cross_month_cache.keys()):
            k_year, k_month = key
            next_ym = self._next_month(k_year, k_month)
            if evicted_ym in (key, next_ym):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            c_era5, c_cmems = self._cross_month_cache.pop(key)
            try:
                c_era5.close()
            except Exception:
                pass
            try:
                c_cmems.close()
            except Exception:
                pass

    def _load_single_month(
        self,
        year: int,
        month: int,
    ) -> tuple[xr.Dataset, xr.Dataset]:
        """Load and validate an ERA5 + CMEMS dataset pair from disk."""
        assert self.weather_yearly_dir is not None
        assert self.ocean_yearly_dir is not None

        era5_path = (
            self.weather_yearly_dir
            / f"era5_wind_{year}-{month:02d}.nc"
        )
        cmems_path = (
            self.ocean_yearly_dir
            / f"med_currents_{year}-{month:02d}.nc"
        )

        if not era5_path.exists():
            raise FileNotFoundError(
                "ERA5 environmental data unavailable "
                f"for {year}-{month:02d}: {era5_path}"
            )

        if not cmems_path.exists():
            raise FileNotFoundError(
                "CMEMS environmental data unavailable "
                f"for {year}-{month:02d}: {cmems_path}"
            )

        new_era5_raw: xr.Dataset | None = None
        new_cmems_raw: xr.Dataset | None = None

        try:
            new_era5_raw = xr.open_dataset(
                era5_path,
                decode_times=True,
                cache=False,
                engine="netcdf4",
            )
            new_cmems_raw = xr.open_dataset(
                cmems_path,
                decode_times=True,
                cache=False,
                engine="netcdf4",
            )
            new_era5 = self._prepare_era5(new_era5_raw)
            new_cmems = self._prepare_cmems(new_cmems_raw)
            return new_era5, new_cmems
        except Exception:
            if new_era5_raw is not None:
                try:
                    new_era5_raw.close()
                except Exception:
                    pass
            if new_cmems_raw is not None:
                try:
                    new_cmems_raw.close()
                except Exception:
                    pass
            raise

    def _get_or_load_month(
        self,
        year: int,
        month: int,
    ) -> tuple[xr.Dataset, xr.Dataset]:
        """Retrieve month from LRU cache or load from disk, evicting if needed."""
        key = (year, month)
        if key in self._month_cache:
            self._month_cache.move_to_end(key)
            return self._month_cache[key]

        new_era5, new_cmems = self._load_single_month(year, month)
        self._month_cache[key] = (new_era5, new_cmems)
        while len(self._month_cache) > self.cache_max_months:
            self._evict_lru_month()
        return new_era5, new_cmems

    def _load_yearly_month(
        self,
        year: int,
        month: int,
    ) -> None:
        """
        Ensure the requested monthly ERA5/CMEMS datasets are loaded and active.
        Uses an LRU cache holding up to cache_max_months entries.
        """
        with self._lock:
            if (
                self._loaded_year == year
                and self._loaded_month == month
                and self.era5 is not None
                and self.cmems is not None
            ):
                return

            self._get_or_load_month(year, month)
            self._set_active_month(year, month)

    def _open_month_datasets(
        self,
        year: int,
        month: int,
    ) -> tuple[xr.Dataset, xr.Dataset]:
        """
        Open a monthly ERA5 + CMEMS pair.
        Kept for backward compatibility; delegates to _get_or_load_month.
        """
        return self._get_or_load_month(year, month)

    def _get_cross_month_datasets(
        self,
        year: int,
        month: int,
    ) -> tuple[xr.Dataset, xr.Dataset]:
        """
        Return the combined (current_month + next_month) concatenated datasets,
        cached in _cross_month_cache to avoid redundant xr.concat calls near boundaries.
        """
        key = (year, month)
        if key in self._cross_month_cache:
            return self._cross_month_cache[key]

        current_era5, current_cmems = self._get_or_load_month(year, month)
        next_year, next_month = self._next_month(year, month)
        next_era5, next_cmems = self._get_or_load_month(next_year, next_month)

        combined_era5 = xr.concat([current_era5, next_era5], dim=self.era5_time)
        combined_cmems = xr.concat([current_cmems, next_cmems], dim=self.cmems_time)

        self._cross_month_cache[key] = (combined_era5, combined_cmems)
        return combined_era5, combined_cmems

    def _ensure_datasets_for_timestamp(
        self,
        timestamp: datetime,
    ) -> None:
        """Ensure the requested month's datasets are loaded."""
        with self._lock:
            if self._single_dataset_mode:

                if (
                    self.era5 is None
                    or self.cmems is None
                ):
                    raise RuntimeError(
                        "Environmental datasets are not loaded."
                    )

                return

            self._load_yearly_month(
                timestamp.year,
                timestamp.month,
            )

    # ==============================================================
    # TIME HELPERS
    # ==============================================================

    @staticmethod
    def _to_naive_utc(
        timestamp: datetime,
    ) -> datetime:
        """
        Convert aware/naive datetime to naive UTC.
        """

        if timestamp.tzinfo is None:
            return timestamp

        return timestamp.astimezone(
            timezone.utc
        ).replace(
            tzinfo=None
        )

    @staticmethod
    def _value(value) -> float:
        """Convert xarray/numpy scalar to Python float."""

        return float(
            np.asarray(value).squeeze()
        )

    # ==============================================================
    # NEXT MONTH
    # ==============================================================

    @staticmethod
    def _next_month(
        year: int,
        month: int,
    ) -> tuple[int, int]:

        if month == 12:
            return year + 1, 1

        return year, month + 1

    # ==============================================================
    # CROSS MONTH LOOKUP
    # ==============================================================

    def _get_velocity_cross_month(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
    ) -> EnvironmentalVelocity:
        """
        Interpolate using the current month's final timestamp
        and the next month's first timestamp.
        """
        with self._lock:
            assert self.era5 is not None
            assert self.cmems is not None
            assert self._loaded_year is not None
            assert self._loaded_month is not None

            req_year = self._loaded_year
            req_month = self._loaded_month

            timestamp64 = np.datetime64(timestamp)

            combined_era5, combined_cmems = self._get_cross_month_datasets(
                req_year,
                req_month,
            )

            # Ensure active month remains the month of the requested timestamp
            self._set_active_month(req_year, req_month)

            era5_lon = self._normalize_longitude(
                longitude,
                self.era5[self.era5_lon].values,
                lon_min=self._era5_lon_min,
                lon_max=self._era5_lon_max,
            )

            cmems_lon = self._normalize_longitude(
                longitude,
                self.cmems[self.cmems_lon].values,
                lon_min=self._cmems_lon_min,
                lon_max=self._cmems_lon_max,
            )

            era5_point = combined_era5.interp(
                {
                    self.era5_lat: latitude,
                    self.era5_lon: era5_lon,
                    self.era5_time: timestamp64,
                },
                method="linear",
            )

            cmems_point = combined_cmems.interp(
                {
                    self.cmems_lat: latitude,
                    self.cmems_lon: cmems_lon,
                    self.cmems_time: timestamp64,
                },
                method="linear",
            )

            return EnvironmentalVelocity(
                wind_u=self._value(era5_point[self.era5_u].values),
                wind_v=self._value(era5_point[self.era5_v].values),
                current_u=self._value(cmems_point[self.cmems_u].values),
                current_v=self._value(cmems_point[self.cmems_v].values),
            )

    def _get_velocities_cross_month(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
        timestamp: datetime,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        with self._lock:
            assert self.era5 is not None
            assert self.cmems is not None
            assert self._loaded_year is not None
            assert self._loaded_month is not None

            req_year = self._loaded_year
            req_month = self._loaded_month

            timestamp64 = np.datetime64(timestamp)

            combined_era5, combined_cmems = self._get_cross_month_datasets(
                req_year,
                req_month,
            )

            self._set_active_month(req_year, req_month)

            era5_longitudes = self.era5[self.era5_lon].values
            cmems_longitudes = self.cmems[self.cmems_lon].values

            era5_lons = np.asarray(
                [self._normalize_longitude(lon, era5_longitudes, lon_min=self._era5_lon_min, lon_max=self._era5_lon_max) for lon in lons],
                dtype=float,
            )
            cmems_lons = np.asarray(
                [self._normalize_longitude(lon, cmems_longitudes, lon_min=self._cmems_lon_min, lon_max=self._cmems_lon_max) for lon in lons],
                dtype=float,
            )

            lats_da = xr.DataArray(lats, dims="points")
            era5_lons_da = xr.DataArray(era5_lons, dims="points")
            cmems_lons_da = xr.DataArray(cmems_lons, dims="points")

            era5_interp_coords = {
                self.era5_lat: lats_da,
                self.era5_lon: era5_lons_da,
                self.era5_time: timestamp64,
            }
            cmems_interp_coords = {
                self.cmems_lat: lats_da,
                self.cmems_lon: cmems_lons_da,
                self.cmems_time: timestamp64,
            }

            wind_u = np.asarray(combined_era5[self.era5_u].interp(era5_interp_coords, method="linear").values)
            wind_v = np.asarray(combined_era5[self.era5_v].interp(era5_interp_coords, method="linear").values)
            current_u = np.asarray(combined_cmems[self.cmems_u].interp(cmems_interp_coords, method="linear").values)
            current_v = np.asarray(combined_cmems[self.cmems_v].interp(cmems_interp_coords, method="linear").values)

            return wind_u, wind_v, current_u, current_v

    # ==============================================================
    # SCALAR LOOKUP
    # ==============================================================

    def get_velocity(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
    ) -> EnvironmentalVelocity:
        """
        Return linearly interpolated environmental velocity at
        a requested latitude, longitude and UTC timestamp.

        Handles month-boundary interpolation.
        """

        if not -90.0 <= latitude <= 90.0:
            raise ValueError(
                f"Invalid latitude: {latitude}"
            )

        timestamp = self._to_naive_utc(
            timestamp
        )

        self._ensure_datasets_for_timestamp(
            timestamp
        )

        assert self.era5 is not None
        assert self.cmems is not None

        # ----------------------------------------------------------
        # Check if requested timestamp exceeds current dataset.
        # ----------------------------------------------------------

        era5_end = np.datetime64(
            self.era5[self.era5_time].values[-1]
        )

        cmems_end = np.datetime64(
            self.cmems[self.cmems_time].values[-1]
        )

        timestamp64 = np.datetime64(
            timestamp
        )

        crosses_boundary = (
            timestamp64 > era5_end
            or timestamp64 > cmems_end
        )

        if crosses_boundary:

            if self._yearly_mode:
                return self._get_velocity_cross_month(
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp,
                )

            raise RuntimeError(
                "Requested timestamp is outside "
                "the loaded environmental dataset."
            )

        # ----------------------------------------------------------
        # Longitude normalization
        # ----------------------------------------------------------

        era5_longitudes = self.era5[
            self.era5_lon
        ].values

        cmems_longitudes = self.cmems[
            self.cmems_lon
        ].values

        # E3: Use cached bounds when available; fall back to computing them.
        era5_lon = self._normalize_longitude(
            longitude,
            era5_longitudes,
            lon_min=self._era5_lon_min,
            lon_max=self._era5_lon_max,
        )

        cmems_lon = self._normalize_longitude(
            longitude,
            cmems_longitudes,
            lon_min=self._cmems_lon_min,
            lon_max=self._cmems_lon_max,
        )


        # ----------------------------------------------------------
        # ERA5 interpolation
        # ----------------------------------------------------------

        era5_point = self.era5.interp(
            {
                self.era5_lat: latitude,
                self.era5_lon: era5_lon,
                self.era5_time: timestamp64,
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
                self.cmems_time: timestamp64,
            },
            method="linear",
        )

        # ----------------------------------------------------------
        # Values
        # ----------------------------------------------------------

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

    # ==============================================================
    # VECTORIZED LOOKUP
    # ==============================================================

    def get_velocities(
        self,
        latitudes: list[float] | np.ndarray,
        longitudes: list[float] | np.ndarray,
        timestamp: datetime,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
    ]:
        """
        Return linearly interpolated environmental velocity for
        multiple points at a single UTC timestamp.

        Returns:

            wind_u,
            wind_v,
            current_u,
            current_v

        as NumPy arrays.
        """

        lats = np.asarray(
            latitudes,
            dtype=float,
        )

        lons = np.asarray(
            longitudes,
            dtype=float,
        )

        if lats.shape != lons.shape:
            raise ValueError(
                "latitudes and longitudes must have "
                "the same shape."
            )

        if not np.all(
            (lats >= -90.0)
            & (lats <= 90.0)
        ):
            raise ValueError(
                "Invalid latitude found in batch."
            )

        timestamp_naive = self._to_naive_utc(
            timestamp
        )

        self._ensure_datasets_for_timestamp(
            timestamp_naive
        )

        assert self.era5 is not None
        assert self.cmems is not None

        # ----------------------------------------------------------
        # Current dataset ends
        # ----------------------------------------------------------

        era5_end = np.datetime64(
            self.era5[self.era5_time].values[-1]
        )

        cmems_end = np.datetime64(
            self.cmems[self.cmems_time].values[-1]
        )

        timestamp64 = np.datetime64(
            timestamp_naive
        )

        crosses_boundary = (
            timestamp64 > era5_end
            or timestamp64 > cmems_end
        )

        # ----------------------------------------------------------
        # Cross-month vectorized lookup
        # ----------------------------------------------------------

        if crosses_boundary:

            if not self._yearly_mode:
                raise RuntimeError(
                    "Requested timestamp is outside "
                    "the loaded environmental dataset."
                )

            # Vectorized cross-month boundary logic
            return self._get_velocities_cross_month(lats, lons, timestamp_naive)

        # ----------------------------------------------------------
        # Longitude normalization
        # ----------------------------------------------------------

        era5_longitudes = self.era5[
            self.era5_lon
        ].values

        cmems_longitudes = self.cmems[
            self.cmems_lon
        ].values

        era5_lons = np.asarray(
            [
                self._normalize_longitude(
                    lon,
                    era5_longitudes,
                )
                for lon in lons
            ],
            dtype=float,
        )

        cmems_lons = np.asarray(
            [
                self._normalize_longitude(
                    lon,
                    cmems_longitudes,
                )
                for lon in lons
            ],
            dtype=float,
        )

        # ----------------------------------------------------------
        # DataArray point coordinates
        # ----------------------------------------------------------

        lats_da = xr.DataArray(
            lats,
            dims="points",
        )

        era5_lons_da = xr.DataArray(
            era5_lons,
            dims="points",
        )

        cmems_lons_da = xr.DataArray(
            cmems_lons,
            dims="points",
        )

        # ----------------------------------------------------------
        # ERA5
        # ----------------------------------------------------------

        era5_interp_coords = {
            self.era5_lat: lats_da,
            self.era5_lon: era5_lons_da,
            self.era5_time: timestamp64,
        }

        wind_u = np.asarray(
            self.era5[self.era5_u].interp(
                era5_interp_coords,
                method="linear",
            ).values
        )

        wind_v = np.asarray(
            self.era5[self.era5_v].interp(
                era5_interp_coords,
                method="linear",
            ).values
        )

        # ----------------------------------------------------------
        # CMEMS
        # ----------------------------------------------------------

        cmems_interp_coords = {
            self.cmems_lat: lats_da,
            self.cmems_lon: cmems_lons_da,
            self.cmems_time: timestamp64,
        }

        current_u = np.asarray(
            self.cmems[self.cmems_u].interp(
                cmems_interp_coords,
                method="linear",
            ).values
        )

        current_v = np.asarray(
            self.cmems[self.cmems_v].interp(
                cmems_interp_coords,
                method="linear",
            ).values
        )

        return (
            wind_u,
            wind_v,
            current_u,
            current_v,
        )

    # ==============================================================
    # LONGITUDE HANDLING
    # ==============================================================

    def _normalize_longitude(
        self,
        longitude: float,
        dataset_longitudes: np.ndarray,
        lon_min: float | None = None,
        lon_max: float | None = None,
    ) -> float:
        """
        Match the longitude convention used by the dataset.

        Handles:

            -180 ... 180

        and:

            0 ... 360

        E3: Accepts cached lon_min/lon_max to avoid repeated np.min/np.max.
        """
        if lon_min is None:
            lon_min = float(np.min(dataset_longitudes))
        if lon_max is None:
            lon_max = float(np.max(dataset_longitudes))

        # Dataset uses 0..360 convention.
        if lon_min >= 0.0 and lon_max > 180.0:
            return longitude % 360.0

        # Dataset uses -180..180 convention.
        return ((longitude + 180.0) % 360.0) - 180.0

    def _normalize_longitude_array(
        self,
        longitudes: np.ndarray,
        dataset_longitudes: np.ndarray,
        lon_min: float | None = None,
        lon_max: float | None = None,
    ) -> np.ndarray:
        """
        E3: Vectorized version of _normalize_longitude for batched lookups.
        """
        if lon_min is None:
            lon_min = float(np.min(dataset_longitudes))
        if lon_max is None:
            lon_max = float(np.max(dataset_longitudes))

        if lon_min >= 0.0 and lon_max > 180.0:
            return longitudes % 360.0

        return ((longitudes + 180.0) % 360.0) - 180.0

    # ==============================================================
    # DESCRIPTION
    # ==============================================================

    def describe(self) -> dict:
        """Return information about currently loaded datasets."""

        if (
            self.era5 is None
            or self.cmems is None
        ):
            return {
                "mode": (
                    "yearly"
                    if self._yearly_mode
                    else "single"
                ),
                "loaded": False,
                "loaded_year": self._loaded_year,
                "loaded_month": self._loaded_month,
            }

        return {
            "mode": (
                "yearly"
                if self._yearly_mode
                else "single"
            ),
            "loaded": True,
            "loaded_year": self._loaded_year,
            "loaded_month": self._loaded_month,
            "era5_dimensions": dict(
                self.era5.sizes
            ),
            "era5_coordinates": list(
                self.era5.coords
            ),
            "era5_variables": list(
                self.era5.data_vars
            ),
            "cmems_dimensions": dict(
                self.cmems.sizes
            ),
            "cmems_coordinates": list(
                self.cmems.coords
            ),
            "cmems_variables": list(
                self.cmems.data_vars
            ),
        }

    # ==============================================================
    # CLEANUP
    # ==============================================================

    def _close_loaded_datasets(self) -> None:
        """Close currently loaded and cached datasets."""
        closed: set[int] = set()

        for c_era5, c_cmems in list(self._cross_month_cache.values()):
            if id(c_era5) not in closed:
                try:
                    c_era5.close()
                except Exception:
                    pass
                closed.add(id(c_era5))
            if id(c_cmems) not in closed:
                try:
                    c_cmems.close()
                except Exception:
                    pass
                closed.add(id(c_cmems))
        self._cross_month_cache.clear()

        for m_era5, m_cmems in list(self._month_cache.values()):
            if id(m_era5) not in closed:
                try:
                    m_era5.close()
                except Exception:
                    pass
                closed.add(id(m_era5))
            if id(m_cmems) not in closed:
                try:
                    m_cmems.close()
                except Exception:
                    pass
                closed.add(id(m_cmems))
        self._month_cache.clear()

        if self.era5 is not None and id(self.era5) not in closed:
            try:
                self.era5.close()
            except Exception:
                pass
            closed.add(id(self.era5))
        self.era5 = None

        if self.cmems is not None and id(self.cmems) not in closed:
            try:
                self.cmems.close()
            except Exception:
                pass
            closed.add(id(self.cmems))
        self.cmems = None

        self._loaded_year = None
        self._loaded_month = None
        self._era5_lon_min = None
        self._era5_lon_max = None
        self._cmems_lon_min = None
        self._cmems_lon_max = None

    def close(self) -> None:
        """Close loaded environmental datasets."""
        with self._lock:
            self._close_loaded_datasets()

    def __enter__(self) -> "WeatherService":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()