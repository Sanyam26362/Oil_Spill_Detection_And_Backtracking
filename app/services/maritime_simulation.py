"""
app/services/maritime_simulation.py

Maritime Kinematic Simulation Engine for Synthetic Mock Vessel Trajectories.
Generates realistic, natural vessel movements using stochastic Ornstein-Uhlenbeck
kinematic drift on SOG/COG, rhumb-line dead reckoning, vessel-type specific
navigation profiles, clean 30-minute temporal sampling, and corridor constraints.
"""

from datetime import datetime, timezone, timedelta
import math
import random
import re
from typing import Dict, Any, List, Tuple, Optional


def snap_to_clean_30min(dt: datetime, round_mode: str = "round") -> datetime:
    """
    Snap a datetime to a clean :00 or :30 boundary with 00 seconds and 00 microseconds.
    """
    total_seconds = dt.minute * 60 + dt.second + dt.microsecond / 1e6
    if round_mode == "floor":
        snapped_min = 0 if dt.minute < 30 else 30
        return dt.replace(minute=snapped_min, second=0, microsecond=0)
    elif round_mode == "ceil":
        if dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
            return dt.replace(second=0, microsecond=0)
        if dt.minute <= 30 and (dt.minute > 0 or dt.second > 0):
            return dt.replace(minute=30, second=0, microsecond=0)
        else:
            base = dt.replace(minute=0, second=0, microsecond=0)
            return base + timedelta(hours=1)
    else:  # round to nearest
        half_hours = round(total_seconds / 1800.0)
        base = dt.replace(minute=0, second=0, microsecond=0)
        return base + timedelta(minutes=int(half_hours * 30))


class MaritimeKinematicSimulator:
    """
    Realistic maritime kinematic simulation model for mock vessel trajectories.
    """

    KM_PER_LAT_DEG = 111.139

    @classmethod
    def haversine_km(
        cls,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Great-circle distance between two WGS-84 coordinates in kilometres."""
        r = 6371.0  # Earth mean radius in km
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)

        a = (
            math.sin(dphi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    @staticmethod
    def _extract_seed(vessel_id: Optional[str]) -> int:
        if not vessel_id:
            return 144
        match = re.search(r"(\d+)$", vessel_id)
        if match:
            return int(match.group(1))
        return 144

    @classmethod
    def simulate_mock_trajectory(
        cls,
        origin_lat: float,
        origin_lon: float,
        release_time: datetime,
        mock_index: int,
        vessel_type: str = "Cargo",
        vessel_id: Optional[str] = None,
        detected_at: Optional[datetime] = None,
        target_distance_km: Optional[float] = None,
        time_difference_hours: Optional[float] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], float]:
        """
        Generate a realistic maritime mock trajectory following the kinematic simulation requirements:
        1. Start: exactly 3h before release_time (snapped to clean :00/:30).
        2. End: exactly 3h after detected_at (or release_time + 6h if missing).
        3. Step: exactly 30 minutes, clean :00 and :30 timestamps.
        4. Vessel-type specific kinematics (Cargo, Tanker, Fishing).
        5. Stochastic SOG/COG process with geodesic dead reckoning and leeway drift.
        6. Corridor constraint (10 - 25 km from backtrack origin at CPA).

        Returns:
            (trajectory, culprit_location, distance_km)
        """
        if release_time.tzinfo is None:
            release_time = release_time.replace(tzinfo=timezone.utc)

        # ------------------------------------------------------------
        # 1. Temporal Window & Clean 30-Minute Waypoints
        # ------------------------------------------------------------
        nominal_start = release_time - timedelta(hours=3)
        start_time = snap_to_clean_30min(nominal_start, "round")

        if detected_at is not None:
            if detected_at.tzinfo is None:
                detected_at = detected_at.replace(tzinfo=timezone.utc)
            nominal_end = detected_at + timedelta(hours=3)
            end_time = snap_to_clean_30min(nominal_end, "round")
        else:
            nominal_end = release_time + timedelta(hours=6)
            end_time = snap_to_clean_30min(nominal_end, "round")

        if end_time < start_time + timedelta(hours=6):
            end_time = start_time + timedelta(hours=6)

        times: List[datetime] = []
        curr = start_time
        while curr <= end_time:
            times.append(curr)
            curr += timedelta(minutes=30)

        num_points = len(times)
        seed = cls._extract_seed(vessel_id) + mock_index * 37
        rng = random.Random(seed)

        # ------------------------------------------------------------
        # 2. Vessel-Type Specific Kinematic Parameters
        # ------------------------------------------------------------
        vtype_lower = (vessel_type or "Cargo").strip().lower()

        if "tanker" in vtype_lower:
            # Tanker: Cruising speed 10.0 - 13.5 knots, ROT < 10°/h (< 5°/30m), consistent SOG
            vmin, vmax = 10.0, 13.5
            mu_v = 11.8
            init_sog = rng.uniform(10.8, 12.5)
            base_cog = 195.0 + rng.uniform(-4.0, 4.0)
            sigma_v = 0.10
            sigma_theta = 1.2
            max_rot = 4.5  # < 10°/hour
            leeway = rng.uniform(1.0, 2.0)
            nominal_bearing = (215.0 + rng.uniform(-10.0, 10.0)) % 360
            default_td = 2.5
        elif "fishing" in vtype_lower:
            # Fishing: Cruising/operating 4.0 - 9.0 knots (drops to 2.5 knots), course swings up to ±25°
            vmin, vmax = 2.5, 9.0
            mu_v = 6.5
            init_sog = rng.uniform(5.5, 7.8)
            base_cog = 180.0 + rng.uniform(-10.0, 10.0)
            sigma_v = 0.40
            sigma_theta = 5.5
            max_rot = 25.0  # swings up to ±25°
            leeway = rng.uniform(2.2, 4.0)
            nominal_bearing = (305.0 + rng.uniform(-10.0, 10.0)) % 360
            default_td = -1.1
        else:
            # Cargo: Cruising speed 12.0 - 16.5 knots, commercial transit lane adherence, steady heading
            vmin, vmax = 12.0, 16.5
            mu_v = 14.2
            init_sog = rng.uniform(13.2, 15.2)
            base_cog = 210.0 + rng.uniform(-4.0, 4.0)
            sigma_v = 0.18
            sigma_theta = 0.9
            max_rot = 2.8
            leeway = rng.uniform(1.2, 2.8)
            nominal_bearing = (125.0 + rng.uniform(-10.0, 10.0)) % 360
            default_td = 1.2

        td_hours = (
            time_difference_hours
            if time_difference_hours is not None
            else default_td
        )

        # ------------------------------------------------------------
        # 3. Corridor Constraint & CPA Anchor (10 - 25 km from origin)
        # ------------------------------------------------------------
        if target_distance_km is not None:
            cpa_dist_km = max(10.0, min(25.0, float(target_distance_km)))
        else:
            cpa_dist_km = 14.0 + (mock_index * 2.5)
            cpa_dist_km = max(10.0, min(25.0, cpa_dist_km))

        # Identify waypoint closest to CPA time: release_time + time_difference_hours
        target_cpa_time = release_time + timedelta(hours=td_hours)
        cpa_idx = min(range(num_points), key=lambda i: abs(times[i] - target_cpa_time))

        # Position at CPA relative to backtrack origin
        rad_bearing = math.radians(nominal_bearing)
        cpa_lat = origin_lat + (cpa_dist_km * math.cos(rad_bearing)) / cls.KM_PER_LAT_DEG
        cos_lat = math.cos(math.radians(origin_lat))
        if abs(cos_lat) < 1e-5:
            cos_lat = 1e-5
        cpa_lon = origin_lon + (cpa_dist_km * math.sin(rad_bearing)) / (cls.KM_PER_LAT_DEG * cos_lat)

        # ------------------------------------------------------------
        # 4. Stochastic Kinematic Simulation & Dead Reckoning
        # ------------------------------------------------------------
        lats = [0.0] * num_points
        lons = [0.0] * num_points
        sogs = [0.0] * num_points
        cogs = [0.0] * num_points
        heads = [0.0] * num_points

        lats[cpa_idx] = cpa_lat
        lons[cpa_idx] = cpa_lon
        sogs[cpa_idx] = init_sog
        cogs[cpa_idx] = base_cog
        heads[cpa_idx] = (base_cog + leeway) % 360

        theta_ou = 0.25  # Mean-reversion rate for SOG

        # Forward propagation from cpa_idx to end
        curr_sog = init_sog
        curr_cog = base_cog
        for i in range(cpa_idx, num_points - 1):
            # OU process on SOG: Mean-reversion + stochastic noise
            dv = theta_ou * (mu_v - curr_sog) * 0.5 + rng.gauss(0, sigma_v)
            curr_sog = max(vmin, min(vmax, curr_sog + dv))

            # Stochastic COG with ROT limit
            dtheta = max(-max_rot, min(max_rot, rng.gauss(0, sigma_theta)))
            curr_cog = (curr_cog + dtheta) % 360
            curr_head = (curr_cog + leeway) % 360

            # Rhumb-line dead reckoning (30 minutes = 0.5 h)
            dd_km = curr_sog * 1.852 * 0.5
            rad_cog = math.radians(curr_cog)
            next_lat = lats[i] + (dd_km * math.cos(rad_cog)) / cls.KM_PER_LAT_DEG
            c_lat = math.cos(math.radians(lats[i]))
            if abs(c_lat) < 1e-5:
                c_lat = 1e-5
            next_lon = lons[i] + (dd_km * math.sin(rad_cog)) / (cls.KM_PER_LAT_DEG * c_lat)

            lats[i + 1] = next_lat
            lons[i + 1] = next_lon
            sogs[i + 1] = curr_sog
            cogs[i + 1] = curr_cog
            heads[i + 1] = curr_head

        # Backward propagation from cpa_idx down to start
        curr_sog = init_sog
        curr_cog = base_cog
        for i in range(cpa_idx, 0, -1):
            dd_km = curr_sog * 1.852 * 0.5
            rad_cog = math.radians(curr_cog)
            prev_lat = lats[i] - (dd_km * math.cos(rad_cog)) / cls.KM_PER_LAT_DEG
            c_lat = math.cos(math.radians(lats[i]))
            if abs(c_lat) < 1e-5:
                c_lat = 1e-5
            prev_lon = lons[i] - (dd_km * math.sin(rad_cog)) / (cls.KM_PER_LAT_DEG * c_lat)

            dv = theta_ou * (mu_v - curr_sog) * 0.5 + rng.gauss(0, sigma_v)
            curr_sog = max(vmin, min(vmax, curr_sog - dv))

            dtheta = max(-max_rot, min(max_rot, rng.gauss(0, sigma_theta)))
            curr_cog = (curr_cog - dtheta) % 360
            curr_head = (curr_cog + leeway) % 360

            lats[i - 1] = prev_lat
            lons[i - 1] = prev_lon
            sogs[i - 1] = curr_sog
            cogs[i - 1] = curr_cog
            heads[i - 1] = curr_head

        # Assemble clean trajectory payload
        trajectory = []
        for i in range(num_points):
            trajectory.append({
                "timestamp": times[i].isoformat().replace("+00:00", "Z"),
                "latitude": round(lats[i], 6),
                "longitude": round(lons[i], 6),
                "speed": round(sogs[i], 1),
                "course": round(cogs[i], 1),
                "heading": round(heads[i], 1),
            })

        # Culprit location at CPA waypoint
        cpa_point = trajectory[cpa_idx]
        actual_dist_km = round(
            cls.haversine_km(
                origin_lat,
                origin_lon,
                cpa_point["latitude"],
                cpa_point["longitude"],
            ),
            3,
        )

        culprit_location = {
            "timestamp": cpa_point["timestamp"],
            "latitude": cpa_point["latitude"],
            "longitude": cpa_point["longitude"],
            "speed": cpa_point["speed"],
            "course": cpa_point["course"],
            "heading": cpa_point["heading"],
        }

        return trajectory, culprit_location, actual_dist_km

    @classmethod
    def sample_real_trajectory(
        cls,
        real_positions: List[Any],
        times: List[datetime],
    ) -> List[Dict[str, Any]]:
        """
        Sample and interpolate real AIS positions to match clean 30-minute waypoints (:00 and :30)
        across the full detection and attribution window.
        """
        if not real_positions or not times:
            return []

        # Extract timestamps in UTC
        p_times: List[datetime] = []
        for p in real_positions:
            t = p.timestamp
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            else:
                t = t.astimezone(timezone.utc)
            p_times.append(t)

        trajectory: List[Dict[str, Any]] = []

        for T in times:
            if T.tzinfo is None:
                T = T.replace(tzinfo=timezone.utc)
            else:
                T = T.astimezone(timezone.utc)

            # If T is before or at the first recorded AIS ping
            if T <= p_times[0]:
                p0 = real_positions[0]
                dt_h = (p_times[0] - T).total_seconds() / 3600.0
                spd = float(p0.speed if p0.speed is not None else 12.0)
                crs = float(p0.course if p0.course is not None else 200.0)
                hdg = float(p0.heading if p0.heading is not None else crs)
                dist_km = spd * 1.852 * dt_h
                rad = math.radians(crs)
                lat = p0.latitude - (dist_km * math.cos(rad)) / cls.KM_PER_LAT_DEG
                c_lat = math.cos(math.radians(p0.latitude))
                if abs(c_lat) < 1e-5:
                    c_lat = 1e-5
                lon = p0.longitude - (dist_km * math.sin(rad)) / (cls.KM_PER_LAT_DEG * c_lat)

                trajectory.append({
                    "timestamp": T.isoformat().replace("+00:00", "Z"),
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "speed": round(spd, 2),
                    "course": round(crs, 2),
                    "heading": round(hdg, 2),
                })
            # If T is after or at the last recorded AIS ping
            elif T >= p_times[-1]:
                pn = real_positions[-1]
                dt_h = (T - p_times[-1]).total_seconds() / 3600.0
                spd = float(pn.speed if pn.speed is not None else 12.0)
                crs = float(pn.course if pn.course is not None else 200.0)
                hdg = float(pn.heading if pn.heading is not None else crs)
                dist_km = spd * 1.852 * dt_h
                rad = math.radians(crs)
                lat = pn.latitude + (dist_km * math.cos(rad)) / cls.KM_PER_LAT_DEG
                c_lat = math.cos(math.radians(pn.latitude))
                if abs(c_lat) < 1e-5:
                    c_lat = 1e-5
                lon = pn.longitude + (dist_km * math.sin(rad)) / (cls.KM_PER_LAT_DEG * c_lat)

                trajectory.append({
                    "timestamp": T.isoformat().replace("+00:00", "Z"),
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "speed": round(spd, 2),
                    "course": round(crs, 2),
                    "heading": round(hdg, 2),
                })
            # Otherwise T is between recorded pings -> linear interpolation
            else:
                idx = 0
                for j in range(len(p_times) - 1):
                    if p_times[j] <= T <= p_times[j + 1]:
                        idx = j
                        break

                p_a, p_b = real_positions[idx], real_positions[idx + 1]
                t_a, t_b = p_times[idx], p_times[idx + 1]
                total_dt = (t_b - t_a).total_seconds()
                alpha = (T - t_a).total_seconds() / total_dt if total_dt > 0 else 0.0

                lat = p_a.latitude + alpha * (p_b.latitude - p_a.latitude)
                lon = p_a.longitude + alpha * (p_b.longitude - p_a.longitude)

                spd_a = float(p_a.speed if p_a.speed is not None else 12.0)
                spd_b = float(p_b.speed if p_b.speed is not None else spd_a)
                spd = spd_a + alpha * (spd_b - spd_a)

                crs_a = float(p_a.course if p_a.course is not None else 200.0)
                crs_b = float(p_b.course if p_b.course is not None else crs_a)
                dc = (crs_b - crs_a + 180) % 360 - 180
                crs = (crs_a + alpha * dc) % 360

                hdg_a = float(p_a.heading if p_a.heading is not None else crs)
                hdg_b = float(p_b.heading if p_b.heading is not None else hdg_a)
                dh = (hdg_b - hdg_a + 180) % 360 - 180
                hdg = (hdg_a + alpha * dh) % 360

                trajectory.append({
                    "timestamp": T.isoformat().replace("+00:00", "Z"),
                    "latitude": round(lat, 6),
                    "longitude": round(lon, 6),
                    "speed": round(spd, 2),
                    "course": round(crs, 2),
                    "heading": round(hdg, 2),
                })

        return trajectory

