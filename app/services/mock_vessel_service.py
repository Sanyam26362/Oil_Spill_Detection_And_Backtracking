import re
from typing import List, Dict, Any, Optional

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
            base_num = 144
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
                "mmsi": f"636{base_num + 1:06d}",
                "imo": f"IMO{9000000 + (base_num + 1) * 7}",
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
                "mmsi": f"215{base_num + 2:06d}",
                "imo": f"IMO{9000000 + (base_num + 2) * 7}",
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
                "mmsi": f"239{base_num + 3:06d}",
                "imo": f"IMO{9000000 + (base_num + 3) * 7}",
                "speed": 8.2,
                "course": 182.1,
                "heading": 182.0,
                "distance_to_origin_km": 19.8,
                "time_difference_hours": -1.1,
                "trajectory_correlation": 0.21
            }
        ]
