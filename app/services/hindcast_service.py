from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.models.drift import (
    ParticleSource,
    SourceEstimate,
)
from app.services.drift_engine import DriftEngine


@dataclass
class SourceDensity:
    """
    A source-probability grid generated from backward particles.
    """

    latitudes: np.ndarray
    longitudes: np.ndarray
    density: np.ndarray


class HindcastService:
    """
    Runs backward particle ensembles and estimates probable
    spill-source locations.
    """

    def __init__(
        self,
        drift_engine: DriftEngine,
    ) -> None:
        self.drift_engine = drift_engine

    @staticmethod
    def _offset_position(
        latitude: float,
        longitude: float,
        east_m: float,
        north_m: float,
    ) -> tuple[float, float]:
        """
        Move a geographic position by east/north distances.
        """

        earth_radius_m = 6_371_000.0

        delta_lat = np.degrees(
            north_m / earth_radius_m
        )

        latitude_rad = np.radians(latitude)

        cos_lat = np.cos(latitude_rad)

        if abs(cos_lat) < 1e-12:
            raise ValueError(
                "Longitude calculation unstable near poles."
            )

        delta_lon = np.degrees(
            east_m / (earth_radius_m * cos_lat)
        )

        return (
            latitude + delta_lat,
            longitude + delta_lon,
        )

    @staticmethod
    def haversine_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:

        earth_radius_km = 6371.0

        lat1_rad = np.radians(lat1)
        lat2_rad = np.radians(lat2)

        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)

        a = (
            np.sin(dlat / 2.0) ** 2
            +
            np.cos(lat1_rad)
            * np.cos(lat2_rad)
            * np.sin(dlon / 2.0) ** 2
        )

        return float(
            earth_radius_km
            * 2.0
            * np.arctan2(
                np.sqrt(a),
                np.sqrt(1.0 - a),
            )
        )

    def backward_ensemble(
        self,
        obs_latitude: float,
        obs_longitude: float,
        obs_time: datetime,
        duration_hours: float,
        ensemble_size: int = 100,
        initial_radius_m: float = 500.0,
        timestep_minutes: int = 15,
        random_seed: int | None = 42,
    ) -> SourceEstimate:
        """
        Generate a backward particle ensemble around the observed
        slick location.
        """

        if ensemble_size <= 0:
            raise ValueError(
                "ensemble_size must be greater than 0."
            )

        if initial_radius_m < 0:
            raise ValueError(
                "initial_radius_m must be >= 0."
            )

        rng = np.random.default_rng(random_seed)

        particles: list[ParticleSource] = []

        for _ in range(ensemble_size):

            # Uniform distribution over the area of a circle.
            angle = rng.uniform(
                0.0,
                2.0 * np.pi,
            )

            radius = (
                initial_radius_m
                * np.sqrt(rng.random())
            )

            east_m = radius * np.cos(angle)
            north_m = radius * np.sin(angle)

            particle_latitude, particle_longitude = (
                self._offset_position(
                    latitude=obs_latitude,
                    longitude=obs_longitude,
                    east_m=east_m,
                    north_m=north_m,
                )
            )

            trajectory = self.drift_engine.backward_drift(
                obs_latitude=particle_latitude,
                obs_longitude=particle_longitude,
                obs_time=obs_time,
                duration_hours=duration_hours,
                timestep_minutes=timestep_minutes,
            )

            if not trajectory.states:
                continue

            source = trajectory.end

            particles.append(
                ParticleSource(
                    latitude=source.latitude,
                    longitude=source.longitude,
                    timestamp=source.timestamp,
                )
            )

        if not particles:
            raise RuntimeError(
                "No valid particles were recovered."
            )

        latitudes = np.array(
            [p.latitude for p in particles]
        )

        longitudes = np.array(
            [p.longitude for p in particles]
        )

        centroid_latitude = float(
            np.mean(latitudes)
        )

        centroid_longitude = float(
            np.mean(longitudes)
        )

        distances = [
            self.haversine_km(
                centroid_latitude,
                centroid_longitude,
                p.latitude,
                p.longitude,
            )
            for p in particles
        ]

        radius_km = float(
            np.max(distances)
        )

        return SourceEstimate(
            particles=particles,
            centroid_latitude=centroid_latitude,
            centroid_longitude=centroid_longitude,
            radius_km=radius_km,
        )

    def build_density_grid(
        self,
        source_estimate: SourceEstimate,
        grid_size: int = 50,
    ) -> SourceDensity:
        """
        Convert recovered particle locations into a simple
        2D histogram.

        This is an initial source-density representation.
        """

        if grid_size < 2:
            raise ValueError(
                "grid_size must be at least 2."
            )

        latitudes = np.array(
            [
                particle.latitude
                for particle in source_estimate.particles
            ]
        )

        longitudes = np.array(
            [
                particle.longitude
                for particle in source_estimate.particles
            ]
        )

        lat_min = float(np.min(latitudes))
        lat_max = float(np.max(latitudes))

        lon_min = float(np.min(longitudes))
        lon_max = float(np.max(longitudes))

        # Avoid zero-width bounds if particles are identical.
        lat_padding = max(
            (lat_max - lat_min) * 0.05,
            1e-6,
        )

        lon_padding = max(
            (lon_max - lon_min) * 0.05,
            1e-6,
        )

        lat_edges = np.linspace(
            lat_min - lat_padding,
            lat_max + lat_padding,
            grid_size + 1,
        )

        lon_edges = np.linspace(
            lon_min - lon_padding,
            lon_max + lon_padding,
            grid_size + 1,
        )

        density, _, _ = np.histogram2d(
            latitudes,
            longitudes,
            bins=[
                lat_edges,
                lon_edges,
            ],
        )

        # Normalize to probability density / particle fraction.
        total = np.sum(density)

        if total > 0:
            density = density / total

        latitude_centers = (
            lat_edges[:-1]
            + np.diff(lat_edges) / 2.0
        )

        longitude_centers = (
            lon_edges[:-1]
            + np.diff(lon_edges) / 2.0
        )

        return SourceDensity(
            latitudes=latitude_centers,
            longitudes=longitude_centers,
            density=density,
        )