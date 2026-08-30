from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from app.models.drift import EnvironmentalVelocity


class WeatherService:
    """
    Provides historical environmental conditions for the drift model.

    Supports:

    1. Existing single-pair datasets, e.g.:
       era5_wind_2019-07-event.nc
       med_currents_2019-07-event.nc

    2. Yearly monthly datasets, e.g.:
       data/weather/raw/yearly/era5_wind_2019-01.nc
       data/ocean/raw/yearly/med_currents_2019-01.nc

    The yearly mode loads only the requested month's datasets and caches
    them. When the requested month changes, the previous month's datasets
    are closed and replaced.

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
        era5_path: str | Path | None = None,
        cmems_path: str | Path | None = None,
        weather_yearly_dir: str | Path | None = None,
        ocean_yearly_dir: str | Path | None = None,
    ) -> None:

        # --------------------------------------------------------------
        # Determine operating mode
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Paths
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Validate single-dataset mode
        # --------------------------------------------------------------

        if self._single_dataset_mode:

            assert self.era5_path is not None
            assert self.cmems_path is not None

            if not self.era5_path.exists():
                raise FileNotFoundError(
                    f"ERA5 dataset not found: "
                    f"{self.era5_path}"
                )

            if not self.cmems_path.exists():
                raise FileNotFoundError(
                    f"CMEMS dataset not found: "
                    f"{self.cmems_path}"
                )

        # --------------------------------------------------------------
        # Validate yearly mode
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Loaded datasets
        # --------------------------------------------------------------

        self.era5: xr.Dataset | None = None
        self.cmems: xr.Dataset | None = None

        # Cached month in yearly mode.
        self._loaded_year: int | None = None
        self._loaded_month: int | None = None

        # --------------------------------------------------------------
        # Coordinate / variable names
        # --------------------------------------------------------------

        self.era5_lat = "latitude"
        self.era5_lon = "longitude"

        # Internally we normalize ERA5 to "time", regardless of whether
        # the source file calls it valid_time or time.
        self.era5_time = "time"

        self.era5_u = "u10"
        self.era5_v = "v10"

        self.cmems_lat = "latitude"
        self.cmems_lon = "longitude"
        self.cmems_time = "time"

        self.cmems_u = "uo"
        self.cmems_v = "vo"

        # --------------------------------------------------------------
        # Load the initial single-dataset pair
        # --------------------------------------------------------------

        if self._single_dataset_mode:
            self._load_single_datasets()

    # ==================================================================
    # DATASET LOADING
    # ==================================================================

    def _load_single_datasets(self) -> None:
        """Load the explicitly supplied ERA5/CMEMS pair."""

        assert self.era5_path is not None
        assert self.cmems_path is not None

        era5 = xr.open_dataset(
            self.era5_path,
            decode_times=True,
        )

        cmems = xr.open_dataset(
            self.cmems_path,
            decode_times=True,
        )

        self.era5 = self._prepare_era5(era5)
        self.cmems = self._prepare_cmems(cmems)

    def _prepare_era5(
        self,
        dataset: xr.Dataset,
    ) -> xr.Dataset:
        """
        Normalize ERA5's time coordinate.

        Your newly downloaded 2019 ERA5 files use:
            valid_time

        while the existing service expects:
            time

        Normalize internally to:
            time
        """

        if "valid_time" in dataset.coords:
            dataset = dataset.rename(
                {"valid_time": "time"}
            )

        elif "valid_time" in dataset.dims:
            dataset = dataset.rename(
                {"valid_time": "time"}
            )

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

        return dataset

    def _load_yearly_month(
        self,
        year: int,
        month: int,
    ) -> None:
        """
        Load the ERA5 and CMEMS datasets for a requested month.

        Only one month is cached at a time.
        """

        if (
            self._loaded_year == year
            and self._loaded_month == month
            and self.era5 is not None
            and self.cmems is not None
        ):
            return

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

        # --------------------------------------------------------------
        # Open new datasets BEFORE closing the old pair.
        #
        # This avoids leaving the service empty if the new pair fails
        # to open.
        # --------------------------------------------------------------

        new_era5_raw: xr.Dataset | None = None
        new_cmems_raw: xr.Dataset | None = None

        try:
            new_era5_raw = xr.open_dataset(
                era5_path,
                decode_times=True,
            )

            new_cmems_raw = xr.open_dataset(
                cmems_path,
                decode_times=True,
            )

            new_era5 = self._prepare_era5(
                new_era5_raw
            )

            new_cmems = self._prepare_cmems(
                new_cmems_raw
            )

        except Exception:
            # _prepare_* may already close the dataset on validation
            # failure, so avoid double-close assumptions here.
            raise

        # --------------------------------------------------------------
        # New pair is valid. Close old pair.
        # --------------------------------------------------------------

        self._close_loaded_datasets()

        self.era5 = new_era5
        self.cmems = new_cmems

        self._loaded_year = year
        self._loaded_month = month

    def _ensure_datasets_for_timestamp(
        self,
        timestamp: datetime,
    ) -> None:
        """
        Ensure the correct environmental datasets are loaded.
        """

        if self._single_dataset_mode:
            if (
                self.era5 is None
                or self.cmems is None
            ):
                raise RuntimeError(
                    "Environmental datasets are not loaded."
                )

            return

        # Yearly mode.
        self._load_yearly_month(
            timestamp.year,
            timestamp.month,
        )

    # ==================================================================
    # TIME HELPERS
    # ==================================================================

    @staticmethod
    def _to_naive_utc(
        timestamp: datetime,
    ) -> datetime:
        """
        Convert an aware/naive datetime into a naive UTC datetime.
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
        """Convert xarray/numpy scalar into Python float."""

        return float(
            np.asarray(value).squeeze()
        )

    # ==================================================================
    # SCALAR LOOKUP
    # ==================================================================

    def get_velocity(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
    ) -> EnvironmentalVelocity:
        """
        Return linearly interpolated environmental velocity at
        a requested latitude, longitude and UTC timestamp.

        This method intentionally remains available as the scalar
        reference implementation.
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

        # --------------------------------------------------------------
        # Longitude normalization
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # ERA5
        # --------------------------------------------------------------

        era5_point = self.era5.interp(
            {
                self.era5_lat: latitude,
                self.era5_lon: era5_lon,
                self.era5_time: timestamp,
            },
            method="linear",
        )

        # --------------------------------------------------------------
        # CMEMS
        # --------------------------------------------------------------

        cmems_point = self.cmems.interp(
            {
                self.cmems_lat: latitude,
                self.cmems_lon: cmems_lon,
                self.cmems_time: timestamp,
            },
            method="linear",
        )

        wind_u = self._value(
            era5_point[
                self.era5_u
            ].values
        )

        wind_v = self._value(
            era5_point[
                self.era5_v
            ].values
        )

        current_u = self._value(
            cmems_point[
                self.cmems_u
            ].values
        )

        current_v = self._value(
            cmems_point[
                self.cmems_v
            ].values
        )

        return EnvironmentalVelocity(
            wind_u=wind_u,
            wind_v=wind_v,
            current_u=current_u,
            current_v=current_v,
        )

    # ==================================================================
    # VECTORIZED LOOKUP
    # ==================================================================

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

        This is the optimized path used by the ensemble drift engine.
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

        timestamp_naive = (
            self._to_naive_utc(
                timestamp
            )
        )

        self._ensure_datasets_for_timestamp(
            timestamp_naive
        )

        assert self.era5 is not None
        assert self.cmems is not None

        # --------------------------------------------------------------
        # Normalize longitudes
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # DataArray point coordinates
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # ERA5 vectorized interpolation
        # --------------------------------------------------------------

        interp_coords = {
            self.era5_lat: lats_da,
            self.era5_lon: era5_lons_da,
            self.era5_time: timestamp_naive,
        }

        wind_u = np.asarray(
            self.era5[self.era5_u].interp(
                interp_coords,
                method="linear",
            ).values
        )

        wind_v = np.asarray(
            self.era5[self.era5_v].interp(
                interp_coords,
                method="linear",
            ).values
        )

        # --------------------------------------------------------------
        # CMEMS vectorized interpolation
        # --------------------------------------------------------------

        cmems_interp_coords = {
            self.cmems_lat: lats_da,
            self.cmems_lon: cmems_lons_da,
            self.cmems_time: timestamp_naive,
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

    # ==================================================================
    # LONGITUDE HANDLING
    # ==================================================================

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

        lon_min = float(
            np.min(dataset_longitudes)
        )

        lon_max = float(
            np.max(dataset_longitudes)
        )

        # Dataset uses 0..360 convention.
        if (
            lon_min >= 0.0
            and lon_max > 180.0
        ):
            return longitude % 360.0

        # Dataset uses -180..180 convention.
        return (
            (
                longitude + 180.0
            )
            % 360.0
        ) - 180.0

    # ==================================================================
    # DEBUGGING / DESCRIPTION
    # ==================================================================

    def describe(self) -> dict:
        """
        Return information about currently loaded datasets.
        """

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

    # ==================================================================
    # CLEANUP
    # ==================================================================

    def _close_loaded_datasets(self) -> None:
        """Close currently loaded datasets."""

        if self.era5 is not None:
            self.era5.close()
            self.era5 = None

        if self.cmems is not None:
            self.cmems.close()
            self.cmems = None

    def close(self) -> None:
        """Close loaded environmental datasets."""

        self._close_loaded_datasets()

        self._loaded_year = None
        self._loaded_month = None

    def __enter__(self) -> "WeatherService":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()