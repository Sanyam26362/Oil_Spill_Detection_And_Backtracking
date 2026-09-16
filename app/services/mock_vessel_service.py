import hashlib
import math
import re
from typing import List, Dict, Any, Optional

# ITU Maritime Identification Digits (MID) for flag states
MID_MAP = {
    "CY": "209",
    "CYPRUS": "209",
    "GR": "239",
    "GREECE": "239",
    "LR": "636",
    "LIBERIA": "636",
    "MT": "215",
    "MALTA": "215",
    "PA": "352",
    "PANAMA": "352",
    "IT": "247",
    "ITALY": "247",
    "MH": "538",
    "MARSHALL ISLANDS": "538",
    "SG": "563",
    "SINGAPORE": "563",
    "BS": "311",
    "BAHAMAS": "311",
    "GB": "232",
    "UK": "232",
    "UNITED KINGDOM": "232",
    "US": "367",
    "USA": "367",
    "UNITED STATES": "367",
    "FR": "227",
    "FRANCE": "227",
    "DE": "211",
    "GERMANY": "211",
    "NL": "244",
    "NETHERLANDS": "244",
    "TR": "271",
    "TURKEY": "271",
    "IN": "419",
    "INDIA": "419",
    "AG": "304",
    "ANTIGUA BARBUDA": "304",
}


def compute_imo_checksum(six_digits: str) -> int:
    """
    Calculate the mandatory IMO 7th digit check digit.
    IMO Resolution A.1078(28) / SOLAS XI-1/3:
    Check digit = sum(digit_i * (8 - i) for i in 1..6) mod 10
    Weights: 7, 6, 5, 4, 3, 2 for the first 6 digits.
    """
    weights = [7, 6, 5, 4, 3, 2]
    total = sum(int(six_digits[i]) * weights[i] for i in range(6))
    return total % 10


def generate_valid_imo(seed_num: int, offset: int = 0) -> str:
    """
    Generate an authentic 7-digit IMO number with a valid check digit.
    Commercial merchant ships are in the 900000 - 999999 range.
    """
    base_val = 920000 + ((seed_num * 13 + offset * 17) % 70000)
    six_digits = f"{base_val:06d}"
    check_digit = compute_imo_checksum(six_digits)
    return f"{six_digits}{check_digit}"


def generate_valid_mmsi(country: Optional[str], seed_num: int, offset: int = 0) -> str:
    """
    Generate an authentic 9-digit MMSI following ITU-R M.585.
    Format: MIDxxxxxx (3-digit country MID + 6-digit ship station identity).
    """
    country_key = (country or "").strip().upper()
    mid = MID_MAP.get(country_key, "215")
    station_num = 200000 + ((seed_num * 137 + offset * 53) % 700000)
    return f"{mid}{station_num:06d}"


def extract_vessel_seed(vessel_id: Optional[str]) -> int:
    """Extract a numeric seed from a vessel ID string."""
    if not vessel_id:
        return 144
    match = re.search(r"(\d+)$", vessel_id)
    if match:
        return int(match.group(1))
    return int(hashlib.md5(vessel_id.encode()).hexdigest()[:6], 16) % 100000


class ForensicSubScoreCalculator:
    """
    Pure, stateless forensic sub-score estimator for use in the /vessels
    endpoint where full AIS trajectory data is not available.

    All formulas mirror those in ScoringEngine so that sub-scores are
    mathematically consistent with how the real culprit is evaluated.
    Sub-scores are bounded to [0.0, 1.0] and rounded to 4 decimal places.

    NOTE: This class NEVER touches the database, ranking logic, or any
    attribution algorithm. It only derives display scores from attributes
    that are already present in the vessel dict.
    """

    # Vessel-type baseline cruising speeds (knots) matching the
    # kinematic profiles in MaritimeKinematicSimulator.
    _BASELINE_SPEEDS: Dict[str, float] = {
        "cargo": 14.2,
        "tanker": 11.8,
        "fishing": 6.5,
        "passenger": 13.0,
    }

    @staticmethod
    def _clamp(value: float) -> float:
        return round(max(0.0, min(1.0, value)), 4)

    @classmethod
    def _baseline_speed(cls, vessel_type: Optional[str]) -> float:
        key = (vessel_type or "").strip().lower()
        for k, v in cls._BASELINE_SPEEDS.items():
            if k in key:
                return v
        return 13.0  # generic merchant

    @classmethod
    def compute(
        cls,
        distance_to_origin_km: Optional[float],
        time_difference_hours: Optional[float],
        speed: Optional[float],
        vessel_type: Optional[str],
        *,
        # Optional hints that shift loiter/approach/departure for realism
        mock_index: int = 0,
    ) -> Dict[str, float]:
        """
        Return a dict with the 6 sub-scores and the weighted `score`.

        Parameters
        ----------
        distance_to_origin_km
            CPA distance from the estimated spill source (km).
        time_difference_hours
            Signed time delta between the vessel's CPA and the estimated
            release time (hours).  Negative = vessel arrived before release.
        speed
            Speed of the vessel at its CPA (knots).
        vessel_type
            String vessel category used to derive a baseline cruising speed.
        mock_index
            0-based index of the mock vessel (0, 1, 2).  Used to add small
            deterministic perturbations so vessels 2-4 look realistically
            distinct from each other.
        """
        dist_km = float(distance_to_origin_km or 15.0)
        td_h = float(time_difference_hours if time_difference_hours is not None else 1.5)
        spd = float(speed or 0.0)
        baseline = cls._baseline_speed(vessel_type)

        # ------------------------------------------------------------------
        # 1. PROXIMITY  –  mirrors: clip(1 - dist / 5, 0, 1)
        #    Real engine uses a 5 km radius; mock vessels sit 10-25 km away
        #    so we scale by 30 km instead so scores spread nicely.
        # ------------------------------------------------------------------
        proximity_score = cls._clamp(1.0 - dist_km / 30.0)

        # ------------------------------------------------------------------
        # 2. TEMPORAL  –  mirrors: clip(1 - |td_min| / 120, 0, 1)
        # ------------------------------------------------------------------
        td_min = abs(td_h) * 60.0
        temporal_score = cls._clamp(1.0 - td_min / 120.0)

        # ------------------------------------------------------------------
        # 3. SLOWDOWN  –  mirrors: clip((baseline - event) / baseline, 0, 1)
        # ------------------------------------------------------------------
        if baseline <= 0.1:
            slowdown_score = 0.0
        else:
            slowdown_score = cls._clamp((baseline - spd) / baseline)

        # ------------------------------------------------------------------
        # 4. LOITER  –  estimated from inverse proximity:
        #    vessels very close to the origin are more likely to have loitered.
        #    Small deterministic perturbation per mock_index for realism.
        # ------------------------------------------------------------------
        loiter_base = cls._clamp(1.0 - dist_km / 20.0)
        loiter_score = cls._clamp(
            loiter_base - mock_index * 0.07
        )

        # ------------------------------------------------------------------
        # 5. APPROACH  –  proportion of pre-event steps where distance
        #    decreased.  Estimated: vessels with low td (arriving close to
        #    release) have a higher approach score.
        # ------------------------------------------------------------------
        approach_score = cls._clamp(
            max(0.0, 1.0 - abs(td_h) / 3.0) - mock_index * 0.05
        )

        # ------------------------------------------------------------------
        # 6. DEPARTURE  –  symmetric to approach but for post-event window.
        # ------------------------------------------------------------------
        departure_score = cls._clamp(
            max(0.0, 1.0 - dist_km / 25.0) - mock_index * 0.05
        )

        # ------------------------------------------------------------------
        # WEIGHTED TOTAL  –  identical weights as ScoringEngine:
        #   0.25 proximity + 0.15 temporal + 0.20 slowdown +
        #   0.15 loiter   + 0.125 approach + 0.125 departure
        # ------------------------------------------------------------------
        total = (
            0.25 * proximity_score
            + 0.15 * temporal_score
            + 0.20 * slowdown_score
            + 0.15 * loiter_score
            + 0.125 * approach_score
            + 0.125 * departure_score
        )

        return {
            "score": round(float(total), 4),
            "proximity_score": proximity_score,
            "temporal_score": temporal_score,
            "slowdown_score": slowdown_score,
            "loiter_score": loiter_score,
            "approach_score": approach_score,
            "departure_score": departure_score,
        }


class MockVesselService:
    @staticmethod
    def get_mock_vessels(
        base_vessel_id: Optional[Any] = None,
        real_vessel: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return exactly 3 deterministically generated mock vessels.
        Names and IDs match the synthetic vessel naming scheme (e.g. SYNTH-Y2019-000145).
        These are strictly for UI demonstration and frontend testing purposes.
        They must NEVER be processed as real candidates or affect scoring.
        """
        if base_vessel_id is not None and not isinstance(base_vessel_id, str):
            real_vessel = base_vessel_id
            base_vessel_id = getattr(real_vessel, "vessel_id", None) or (
                real_vessel.get("vessel_id") if isinstance(real_vessel, dict) else None
            )

        if base_vessel_id is None and real_vessel is not None:
            base_vessel_id = getattr(real_vessel, "vessel_id", None) or (
                real_vessel.get("vessel_id") if isinstance(real_vessel, dict) else None
            )

        match = re.match(r"^(.*?)-(\d+)$", base_vessel_id or "")
        if match:
            prefix = match.group(1)
            base_num = int(match.group(2))
            num_digits = len(match.group(2))
        else:
            prefix = "SYNTH-Y2019"
            base_num = extract_vessel_seed(base_vessel_id)
            num_digits = 6

        id_1 = f"{prefix}-{base_num + 1:0{num_digits}d}"
        id_2 = f"{prefix}-{base_num + 2:0{num_digits}d}"
        id_3 = f"{prefix}-{base_num + 3:0{num_digits}d}"

        # Base mock distances around the real candidate distance, clamped
        # into the outer attribution search corridor (10 - 25 km)
        base_dist = None
        if real_vessel is not None:
            base_dist = getattr(real_vessel, "distance_to_origin_km", None)
            if base_dist is None and isinstance(real_vessel, dict):
                base_dist = real_vessel.get("distance_to_origin_km")
        base_dist = max(12.5, min(22.5, float(base_dist or 15.0)))

        dist_1 = round(base_dist + ((-1) ** 1 * (1 * 0.7)), 2)
        dist_2 = round(base_dist + ((-1) ** 2 * (2 * 0.7)), 2)
        dist_3 = round(base_dist + ((-1) ** 3 * (3 * 0.7)), 2)

        return [
            {
                "vessel_id": id_1,
                "is_mock": True,
                "is_mock_comparison": True,
                "rank": 2,
                "vessel_name": id_1,
                "country": "LR",
                "shiptype": 70,
                "shiptype_name": "Cargo, all ships of this type",
                "vessel_type": "Cargo",
                "mmsi": generate_valid_mmsi("LR", base_num, offset=1),
                "imo": generate_valid_imo(base_num, offset=1),
                "speed": 13.4,
                "course": 210.2,
                "heading": 212.0,
                "distance_to_origin_km": dist_1,
                "time_difference_hours": 1.2,
                "trajectory_correlation": None,
                **ForensicSubScoreCalculator.compute(
                    distance_to_origin_km=dist_1,
                    time_difference_hours=1.2,
                    speed=13.4,
                    vessel_type="Cargo",
                    mock_index=0,
                ),
            },
            {
                "vessel_id": id_2,
                "is_mock": True,
                "is_mock_comparison": True,
                "rank": 3,
                "vessel_name": id_2,
                "country": "MT",
                "shiptype": 80,
                "shiptype_name": "Tanker, all ships of this type",
                "vessel_type": "Tanker",
                "mmsi": generate_valid_mmsi("MT", base_num, offset=2),
                "imo": generate_valid_imo(base_num, offset=2),
                "speed": 11.2,
                "course": 195.0,
                "heading": 196.5,
                "distance_to_origin_km": dist_2,
                "time_difference_hours": 2.5,
                "trajectory_correlation": None,
                **ForensicSubScoreCalculator.compute(
                    distance_to_origin_km=dist_2,
                    time_difference_hours=2.5,
                    speed=11.2,
                    vessel_type="Tanker",
                    mock_index=1,
                ),
            },
            {
                "vessel_id": id_3,
                "is_mock": True,
                "is_mock_comparison": True,
                "rank": 4,
                "vessel_name": id_3,
                "country": "GR",
                "shiptype": 30,
                "shiptype_name": "Fishing",
                "vessel_type": "Fishing",
                "mmsi": generate_valid_mmsi("GR", base_num, offset=3),
                "imo": generate_valid_imo(base_num, offset=3),
                "speed": 6.8,
                "course": 182.0,
                "heading": 184.5,
                "distance_to_origin_km": dist_3,
                "time_difference_hours": -1.1,
                "trajectory_correlation": None,
                **ForensicSubScoreCalculator.compute(
                    distance_to_origin_km=dist_3,
                    time_difference_hours=-1.1,
                    speed=6.8,
                    vessel_type="Fishing",
                    mock_index=2,
                ),
            },
        ]
