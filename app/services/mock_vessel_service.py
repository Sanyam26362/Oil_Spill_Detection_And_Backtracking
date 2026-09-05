import hashlib
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


class MockVesselService:
    @staticmethod
    def get_mock_vessels(base_vessel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return exactly 3 deterministically generated mock vessels.
        Names and IDs match the synthetic vessel naming scheme (e.g. SYNTH-Y2019-000145).
        These are strictly for UI demonstration and frontend testing purposes.
        They must NEVER be processed as real candidates or affect scoring.
        """
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

        return [
            {
                "vessel_id": id_1,
                "is_mock": True,
                "rank": 2,
                "score": None,
                "vessel_name": id_1,
                "country": "Liberia",
                "shiptype": 70,
                "shiptype_name": "Cargo, all ships of this type",
                "vessel_type": "Cargo",
                "mmsi": generate_valid_mmsi("Liberia", base_num, offset=1),
                "imo": generate_valid_imo(base_num, offset=1),
                "speed": 12.5,
                "course": 208.5,
                "heading": 208.0,
                "distance_to_origin_km": 12.5,
                "time_difference_hours": 1.2,
                "trajectory_correlation": 0.45
            },
            {
                "vessel_id": id_2,
                "is_mock": True,
                "rank": 3,
                "score": None,
                "vessel_name": id_2,
                "country": "Malta",
                "shiptype": 80,
                "shiptype_name": "Tanker, all ships of this type",
                "vessel_type": "Tanker",
                "mmsi": generate_valid_mmsi("Malta", base_num, offset=2),
                "imo": generate_valid_imo(base_num, offset=2),
                "speed": 10.8,
                "course": 195.2,
                "heading": 195.0,
                "distance_to_origin_km": 15.3,
                "time_difference_hours": 2.5,
                "trajectory_correlation": 0.32
            },
            {
                "vessel_id": id_3,
                "is_mock": True,
                "rank": 4,
                "score": None,
                "vessel_name": id_3,
                "country": "Greece",
                "shiptype": 30,
                "shiptype_name": "Fishing",
                "vessel_type": "Fishing",
                "mmsi": generate_valid_mmsi("Greece", base_num, offset=3),
                "imo": generate_valid_imo(base_num, offset=3),
                "speed": 8.2,
                "course": 182.1,
                "heading": 182.0,
                "distance_to_origin_km": 19.8,
                "time_difference_hours": -1.1,
                "trajectory_correlation": 0.21
            }
        ]
