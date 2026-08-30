from __future__ import annotations

from pathlib import Path
import numpy as np
import xarray as xr


class OceanMask:
    """
    Spatial ocean mask derived from the CMEMS current grid.

    A grid cell is considered ocean when both uo and vo have finite
    values at the selected reference time.
    """

    def __init__(self, cmems_path: str | Path):
        self.cmems_path = Path(cmems_path)

        self.ds = xr.open_dataset(self.cmems_path)

        if "uo" not in self.ds or "vo" not in self.ds:
            self.ds.close()
            raise ValueError(
                "CMEMS dataset must contain 'uo' and 'vo'."
            )

        self.lat_name = (
            "latitude"
            if "latitude" in self.ds.coords
            else "lat"
        )

        self.lon_name = (
            "longitude"
            if "longitude" in self.ds.coords
            else "lon"
        )

        if self.lat_name not in self.ds.coords:
            self.close()
            raise ValueError(
                "CMEMS latitude coordinate not found."
            )

        if self.lon_name not in self.ds.coords:
            self.close()
            raise ValueError(
                "CMEMS longitude coordinate not found."
            )

        # Use the first available time slice as the spatial mask.
        uo = self.ds["uo"]

        if "time" in uo.dims:
            uo = uo.isel(time=0)

        vo = self.ds["vo"]

        if "time" in vo.dims:
            vo = vo.isel(time=0)

        # Reduce remaining non-spatial dimensions if necessary.
        while self.lat_name not in uo.dims or self.lon_name not in uo.dims:
            extra_dims = [
                d
                for d in uo.dims
                if d not in {
                    self.lat_name,
                    self.lon_name,
                }
            ]

            if not extra_dims:
                break

            uo = uo.isel(
                {
                    extra_dims[0]: 0
                }
            )

        while self.lat_name not in vo.dims or self.lon_name not in vo.dims:
            extra_dims = [
                d
                for d in vo.dims
                if d not in {
                    self.lat_name,
                    self.lon_name,
                }
            ]

            if not extra_dims:
                break

            vo = vo.isel(
                {
                    extra_dims[0]: 0
                }
            )

        self.latitudes = np.asarray(
            self.ds[self.lat_name].values,
            dtype=float,
        )

        self.longitudes = np.asarray(
            self.ds[self.lon_name].values,
            dtype=float,
        )

        self.mask = (
            np.isfinite(uo.values)
            & np.isfinite(vo.values)
        )

        if self.mask.ndim != 2:
            raise ValueError(
                f"Expected a 2D ocean mask, got "
                f"shape={self.mask.shape}."
            )

    def _nearest_indices(
        self,
        latitude: float,
        longitude: float,
    ) -> tuple[int, int]:
        lat_idx = int(
            np.abs(
                self.latitudes - latitude
            ).argmin()
        )

        lon_idx = int(
            np.abs(
                self.longitudes - longitude
            ).argmin()
        )

        return lat_idx, lon_idx

    def is_ocean(
        self,
        latitude: float,
        longitude: float,
    ) -> bool:
        """
        Return True when the nearest CMEMS grid cell is valid ocean.
        """
        lat_idx, lon_idx = (
            self._nearest_indices(
                latitude,
                longitude,
            )
        )

        return bool(
            self.mask[
                lat_idx,
                lon_idx
            ]
        )

    def sample_ocean_point(
        self,
        rng: np.random.Generator,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        max_attempts: int = 10_000,
    ) -> tuple[float, float]:
        """
        Randomly sample an ocean point inside the requested bounds.
        """
        for _ in range(max_attempts):
            latitude = float(
                rng.uniform(
                    lat_min,
                    lat_max,
                )
            )

            longitude = float(
                rng.uniform(
                    lon_min,
                    lon_max,
                )
            )

            if self.is_ocean(
                latitude,
                longitude,
            ):
                return latitude, longitude

        raise RuntimeError(
            "Unable to find a valid ocean point "
            f"after {max_attempts} attempts."
        )

    def close(self) -> None:
        self.ds.close()

    def __enter__(self) -> "OceanMask":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()