from __future__ import annotations

from datetime import datetime, timedelta
import logging

import numpy as np


from app.services.weather_service import WeatherService

from app.models.drift import (
    DriftTrajectory,
    ParticleState,
)

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0


class DriftEngine:
    """
    Oil surface drift and particle-tracking engine.

    Basic model:

        drift = ocean current + windage * wind

    u = east-west velocity (m/s)
    v = north-south velocity (m/s)
    """

    def __init__(
        self,
        weather_service: WeatherService,
        windage: float = 0.03,
    ) -> None:

        if windage < 0:
            raise ValueError("Windage must be >= 0.")

        self.weather_service = weather_service
        self.windage = windage

    @staticmethod
    def move_particle(
        latitude: float,
        longitude: float,
        u: float,
        v: float,
        seconds: float,
    ) -> tuple[float, float]:
        """
        Move a particle using horizontal velocity in m/s.

        Positive u -> east
        Negative u -> west
        Positive v -> north
        Negative v -> south

        A negative `seconds` value performs backward movement.
        """

        north_distance = v * seconds
        east_distance = u * seconds

        delta_lat = np.degrees(
            north_distance / EARTH_RADIUS_M
        )

        latitude_rad = np.radians(latitude)
        cos_lat = np.cos(latitude_rad)

        if abs(cos_lat) < 1e-12:
            raise ValueError(
                "Longitude calculation is unstable near the poles."
            )

        delta_lon = np.degrees(
            east_distance
            / (EARTH_RADIUS_M * cos_lat)
        )

        return (
            latitude + delta_lat,
            longitude + delta_lon,
        )

    @staticmethod
    def move_particles(
        latitudes: np.ndarray,
        longitudes: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        seconds: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Move multiple particles using horizontal velocity in m/s.
        """
        north_distance = v * seconds
        east_distance = u * seconds

        delta_lat = np.degrees(north_distance / EARTH_RADIUS_M)

        latitude_rad = np.radians(latitudes)
        cos_lat = np.cos(latitude_rad)

        if np.any(np.abs(cos_lat) < 1e-12):
            raise ValueError(
                "Longitude calculation is unstable near the poles."
            )

        delta_lon = np.degrees(
            east_distance / (EARTH_RADIUS_M * cos_lat)
        )

        return (
            latitudes + delta_lat,
            longitudes + delta_lon,
        )

    def _track(
        self,
        start_latitude: float,
        start_longitude: float,
        start_time: datetime,
        duration_hours: float,
        timestep_minutes: int,
        direction: str,
    ) -> DriftTrajectory:

        if duration_hours <= 0:
            raise ValueError(
                "duration_hours must be greater than 0."
            )

        if timestep_minutes <= 0:
            raise ValueError(
                "timestep_minutes must be greater than 0."
            )

        if direction not in {"forward", "backward"}:
            raise ValueError(
                "direction must be 'forward' or 'backward'."
            )

        time_multiplier = (
            1 if direction == "forward" else -1
        )

        timestep_seconds = (
            timestep_minutes
            * 60
            * time_multiplier
        )

        number_of_steps = int(
            duration_hours * 3600
            / abs(timestep_seconds)
        )

        latitude = start_latitude
        longitude = start_longitude
        timestamp = start_time

        states: list[ParticleState] = []

        # ----------------------------------------------------------
        # Store the INITIAL state.
        #
        # We need environmental data at this point because it is
        # the velocity used for the first integration step.
        # ----------------------------------------------------------

        environment = self.weather_service.get_velocity(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
        )

        initial_values = (
            environment.wind_u,
            environment.wind_v,
            environment.current_u,
            environment.current_v,
        )

        if any(
            np.isnan(value)
            for value in initial_values
        ):
            logger.warning(
                "Tracking could not start: "
                "environmental data unavailable at "
                "lat=%f lon=%f time=%s",
                latitude,
                longitude,
                timestamp,
            )

            return DriftTrajectory(states=[])

        drift_u = (
            environment.current_u
            + self.windage * environment.wind_u
        )

        drift_v = (
            environment.current_v
            + self.windage * environment.wind_v
        )

        states.append(
            ParticleState(
                timestamp=timestamp,
                latitude=latitude,
                longitude=longitude,
                wind_u=environment.wind_u,
                wind_v=environment.wind_v,
                current_u=environment.current_u,
                current_v=environment.current_v,
                drift_u=drift_u,
                drift_v=drift_v,
            )
        )

        # ----------------------------------------------------------
        # Integrate one timestep at a time.
        # ----------------------------------------------------------

        for step in range(number_of_steps):

            # Move using the velocity associated with the current
            # state.
            new_latitude, new_longitude = (
                self.move_particle(
                    latitude=latitude,
                    longitude=longitude,
                    u=drift_u,
                    v=drift_v,
                    seconds=timestep_seconds,
                )
            )

            new_timestamp = timestamp + timedelta(
                seconds=timestep_seconds
            )

            latitude = new_latitude
            longitude = new_longitude
            timestamp = new_timestamp

            # Get the environmental conditions at the NEW state.
            environment = self.weather_service.get_velocity(
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
            )

            values = (
                environment.wind_u,
                environment.wind_v,
                environment.current_u,
                environment.current_v,
            )

            if any(
                np.isnan(value)
                for value in values
            ):
                logger.warning(
                    "Tracking stopped at step %d: "
                    "environmental data unavailable at "
                    "lat=%f lon=%f time=%s",
                    step,
                    latitude,
                    longitude,
                    timestamp,
                )
                break

            drift_u = (
                environment.current_u
                + self.windage * environment.wind_u
            )

            drift_v = (
                environment.current_v
                + self.windage * environment.wind_v
            )

            states.append(
                ParticleState(
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    wind_u=environment.wind_u,
                    wind_v=environment.wind_v,
                    current_u=environment.current_u,
                    current_v=environment.current_v,
                    drift_u=drift_u,
                    drift_v=drift_v,
                )
            )

        # ----------------------------------------------------------
        # Remainder step
        #
        # If duration_hours has a fractional part (e.g. 40.1 h =
        # 40 h 6 min), the integer division above silently drops the
        # residual.  We execute one final partial step so the
        # trajectory endpoint aligns with the hindcast source centroid.
        # ----------------------------------------------------------

        total_duration_seconds = duration_hours * 3600.0
        abs_timestep = abs(timestep_seconds)
        remainder_seconds = total_duration_seconds % abs_timestep

        if remainder_seconds > 1.0:  # guard against floating-point noise
            remainder_dt = remainder_seconds * time_multiplier

            new_latitude, new_longitude = self.move_particle(
                latitude=latitude,
                longitude=longitude,
                u=drift_u,
                v=drift_v,
                seconds=remainder_dt,
            )

            new_timestamp = timestamp + timedelta(seconds=remainder_dt)

            latitude = new_latitude
            longitude = new_longitude
            timestamp = new_timestamp

            environment = self.weather_service.get_velocity(
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
            )

            remainder_values = (
                environment.wind_u,
                environment.wind_v,
                environment.current_u,
                environment.current_v,
            )

            if not any(np.isnan(v) for v in remainder_values):
                drift_u = (
                    environment.current_u
                    + self.windage * environment.wind_u
                )
                drift_v = (
                    environment.current_v
                    + self.windage * environment.wind_v
                )
                states.append(
                    ParticleState(
                        timestamp=timestamp,
                        latitude=latitude,
                        longitude=longitude,
                        wind_u=environment.wind_u,
                        wind_v=environment.wind_v,
                        current_u=environment.current_u,
                        current_v=environment.current_v,
                        drift_u=drift_u,
                        drift_v=drift_v,
                    )
                )
            else:
                logger.warning(
                    "Remainder step skipped: "
                    "environmental data unavailable at "
                    "lat=%f lon=%f time=%s",
                    latitude,
                    longitude,
                    timestamp,
                )

        return DriftTrajectory(states=states)

    def _track_ensemble(
        self,
        start_latitudes: np.ndarray | list[float],
        start_longitudes: np.ndarray | list[float],
        start_time: datetime,
        duration_hours: float,
        timestep_minutes: int,
        direction: str,
        include_history: bool = True,
    ) -> list[DriftTrajectory]:

        if duration_hours <= 0:
            raise ValueError("duration_hours must be greater than 0.")
        if timestep_minutes <= 0:
            raise ValueError("timestep_minutes must be greater than 0.")
        if direction not in {"forward", "backward"}:
            raise ValueError("direction must be 'forward' or 'backward'.")

        time_multiplier = 1 if direction == "forward" else -1
        timestep_seconds = timestep_minutes * 60 * time_multiplier
        number_of_steps = int(duration_hours * 3600 / abs(timestep_seconds))

        lats = np.asarray(start_latitudes, dtype=float)
        lons = np.asarray(start_longitudes, dtype=float)
        num_particles = len(lats)

        active = np.ones(num_particles, dtype=bool)
        history: list[list[ParticleState]] = [[] for _ in range(num_particles)]
        timestamp = start_time

        wind_u, wind_v, curr_u, curr_v = self.weather_service.get_velocities(
            latitudes=lats,
            longitudes=lons,
            timestamp=timestamp,
        )

        valid_idx = ~np.isnan(wind_u) & ~np.isnan(wind_v) & ~np.isnan(curr_u) & ~np.isnan(curr_v)

        for idx in np.where(~valid_idx)[0]:
            active[idx] = False
            logger.warning(
                "Tracking could not start for particle %d: "
                "environmental data unavailable at lat=%f lon=%f time=%s",
                idx, lats[idx], lons[idx], timestamp
            )

        drift_u = np.zeros(num_particles)
        drift_v = np.zeros(num_particles)

        drift_u[valid_idx] = curr_u[valid_idx] + self.windage * wind_u[valid_idx]
        drift_v[valid_idx] = curr_v[valid_idx] + self.windage * wind_v[valid_idx]

        if include_history:
            for idx in np.where(valid_idx)[0]:
                history[idx].append(
                    ParticleState(
                        timestamp=timestamp,
                        latitude=float(lats[idx]),
                        longitude=float(lons[idx]),
                        wind_u=float(wind_u[idx]),
                        wind_v=float(wind_v[idx]),
                        current_u=float(curr_u[idx]),
                        current_v=float(curr_v[idx]),
                        drift_u=float(drift_u[idx]),
                        drift_v=float(drift_v[idx]),
                    )
                )
        else:
            last_timestamp = [timestamp if valid_idx[i] else None for i in range(num_particles)]
            last_lat = lats.copy()
            last_lon = lons.copy()
            last_wind_u = wind_u.copy()
            last_wind_v = wind_v.copy()
            last_curr_u = curr_u.copy()
            last_curr_v = curr_v.copy()
            last_drift_u = drift_u.copy()
            last_drift_v = drift_v.copy()

        for step in range(number_of_steps):
            if not np.any(active):
                break

            active_idx = np.where(active)[0]

            new_lats, new_lons = self.move_particles(
                latitudes=lats[active_idx],
                longitudes=lons[active_idx],
                u=drift_u[active_idx],
                v=drift_v[active_idx],
                seconds=timestep_seconds,
            )

            lats[active_idx] = new_lats
            lons[active_idx] = new_lons

            new_timestamp = timestamp + timedelta(seconds=timestep_seconds)
            timestamp = new_timestamp

            wind_u_new, wind_v_new, curr_u_new, curr_v_new = self.weather_service.get_velocities(
                latitudes=lats[active_idx],
                longitudes=lons[active_idx],
                timestamp=timestamp,
            )

            step_valid = ~np.isnan(wind_u_new) & ~np.isnan(wind_v_new) & ~np.isnan(curr_u_new) & ~np.isnan(curr_v_new)

            # E4: Vectorize drift velocity update over active particles
            step_d_u = curr_u_new + self.windage * wind_u_new
            step_d_v = curr_v_new + self.windage * wind_v_new
            drift_u[active_idx[step_valid]] = step_d_u[step_valid]
            drift_v[active_idx[step_valid]] = step_d_v[step_valid]

            for i, idx in enumerate(active_idx):
                if not step_valid[i]:
                    active[idx] = False
                    logger.warning(
                        "Tracking stopped at step %d for particle %d: "
                        "environmental data unavailable at lat=%f lon=%f time=%s",
                        step, idx, lats[idx], lons[idx], timestamp
                    )
                else:
                    if include_history:
                        history[idx].append(
                            ParticleState(
                                timestamp=timestamp,
                                latitude=float(lats[idx]),
                                longitude=float(lons[idx]),
                                wind_u=float(wind_u_new[i]),
                                wind_v=float(wind_v_new[i]),
                                current_u=float(curr_u_new[i]),
                                current_v=float(curr_u_new[i]),
                                drift_u=float(step_d_u[i]),
                                drift_v=float(step_d_v[i]),
                            )
                        )
                    else:
                        last_timestamp[idx] = timestamp
                        last_lat[idx] = lats[idx]
                        last_lon[idx] = lons[idx]
                        last_wind_u[idx] = wind_u_new[i]
                        last_wind_v[idx] = wind_v_new[i]
                        last_curr_u[idx] = curr_u_new[i]
                        last_curr_v[idx] = curr_v_new[i]
                        last_drift_u[idx] = step_d_u[i]
                        last_drift_v[idx] = step_d_v[i]

        # ----------------------------------------------------------
        # Ensemble remainder step
        #
        # Mirrors the scalar _track() remainder logic.  Ensures all
        # active particles reach the full integration duration even
        # when duration_hours has a fractional part.
        # ----------------------------------------------------------

        total_duration_seconds = duration_hours * 3600.0
        abs_timestep = abs(timestep_seconds)
        remainder_seconds = total_duration_seconds % abs_timestep

        if remainder_seconds > 1.0 and np.any(active):
            remainder_dt = remainder_seconds * time_multiplier
            active_idx = np.where(active)[0]

            new_lats, new_lons = self.move_particles(
                latitudes=lats[active_idx],
                longitudes=lons[active_idx],
                u=drift_u[active_idx],
                v=drift_v[active_idx],
                seconds=remainder_dt,
            )

            lats[active_idx] = new_lats
            lons[active_idx] = new_lons

            timestamp = timestamp + timedelta(seconds=remainder_dt)

            wind_u_r, wind_v_r, curr_u_r, curr_v_r = self.weather_service.get_velocities(
                latitudes=lats[active_idx],
                longitudes=lons[active_idx],
                timestamp=timestamp,
            )

            rem_valid = (
                ~np.isnan(wind_u_r)
                & ~np.isnan(wind_v_r)
                & ~np.isnan(curr_u_r)
                & ~np.isnan(curr_v_r)
            )

            # E4: Vectorize remainder drift velocity update over active particles
            rem_d_u = curr_u_r + self.windage * wind_u_r
            rem_d_v = curr_v_r + self.windage * wind_v_r
            drift_u[active_idx[rem_valid]] = rem_d_u[rem_valid]
            drift_v[active_idx[rem_valid]] = rem_d_v[rem_valid]

            for i, idx in enumerate(active_idx):
                if not rem_valid[i]:
                    logger.warning(
                        "Remainder step skipped for particle %d: "
                        "environmental data unavailable at lat=%f lon=%f time=%s",
                        idx, lats[idx], lons[idx], timestamp,
                    )
                else:
                    if include_history:
                        history[idx].append(
                            ParticleState(
                                timestamp=timestamp,
                                latitude=float(lats[idx]),
                                longitude=float(lons[idx]),
                                wind_u=float(wind_u_r[i]),
                                wind_v=float(wind_v_r[i]),
                                current_u=float(curr_u_r[i]),
                                current_v=float(curr_v_r[i]),
                                drift_u=float(rem_d_u[i]),
                                drift_v=float(rem_d_v[i]),
                            )
                        )
                    else:
                        last_timestamp[idx] = timestamp
                        last_lat[idx] = lats[idx]
                        last_lon[idx] = lons[idx]
                        last_wind_u[idx] = wind_u_r[i]
                        last_wind_v[idx] = wind_v_r[i]
                        last_curr_u[idx] = curr_u_r[i]
                        last_curr_v[idx] = curr_v_r[i]
                        last_drift_u[idx] = rem_d_u[i]
                        last_drift_v[idx] = rem_d_v[i]

        if not include_history:
            for idx in range(num_particles):
                if last_timestamp[idx] is not None:
                    history[idx] = [
                        ParticleState(
                            timestamp=last_timestamp[idx],
                            latitude=float(last_lat[idx]),
                            longitude=float(last_lon[idx]),
                            wind_u=float(last_wind_u[idx]),
                            wind_v=float(last_wind_v[idx]),
                            current_u=float(last_curr_u[idx]),
                            current_v=float(last_curr_v[idx]),
                            drift_u=float(last_drift_u[idx]),
                            drift_v=float(last_drift_v[idx]),
                        )
                    ]

        return [DriftTrajectory(states=states) for states in history]

    def forward_drift(
        self,
        start_latitude: float,
        start_longitude: float,
        start_time: datetime,
        duration_hours: float,
        timestep_minutes: int = 15,
    ) -> DriftTrajectory:
        """
        Simulate oil movement forward in time.
        """

        return self._track(
            start_latitude=start_latitude,
            start_longitude=start_longitude,
            start_time=start_time,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
            direction="forward",
        )

    def backward_drift(
        self,
        obs_latitude: float,
        obs_longitude: float,
        obs_time: datetime,
        duration_hours: float,
        timestep_minutes: int = 15,
    ) -> DriftTrajectory:
        """
        Hindcast backwards from an observed slick.
        """

        return self._track(
            start_latitude=obs_latitude,
            start_longitude=obs_longitude,
            start_time=obs_time,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
            direction="backward",
        )

    def forward_drift_ensemble(
        self,
        start_latitudes: np.ndarray | list[float],
        start_longitudes: np.ndarray | list[float],
        start_time: datetime,
        duration_hours: float,
        timestep_minutes: int = 15,
        include_history: bool = True,
    ) -> list[DriftTrajectory]:
        """
        Simulate oil movement forward in time for multiple particles.
        """
        return self._track_ensemble(
            start_latitudes=start_latitudes,
            start_longitudes=start_longitudes,
            start_time=start_time,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
            direction="forward",
            include_history=include_history,
        )

    def backward_drift_ensemble(
        self,
        obs_latitudes: np.ndarray | list[float],
        obs_longitudes: np.ndarray | list[float],
        obs_time: datetime,
        duration_hours: float,
        timestep_minutes: int = 15,
        include_history: bool = True,
    ) -> list[DriftTrajectory]:
        """
        Hindcast backwards for multiple observed slick points.
        """
        return self._track_ensemble(
            start_latitudes=obs_latitudes,
            start_longitudes=obs_longitudes,
            start_time=obs_time,
            duration_hours=duration_hours,
            timestep_minutes=timestep_minutes,
            direction="backward",
            include_history=include_history,
        )

    @staticmethod
    def haversine_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calculate great-circle distance between two coordinates.
        """

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

        c = 2.0 * np.arctan2(
            np.sqrt(a),
            np.sqrt(1.0 - a),
        )

        return float(6371.0 * c)