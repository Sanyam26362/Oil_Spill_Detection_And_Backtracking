from typing import List, Dict, Any

class MockVesselService:
    @staticmethod
    def get_mock_vessels() -> List[Dict[str, Any]]:
        """
        Return exactly 3 deterministically generated mock vessels.
        These are strictly for UI demonstration and frontend testing purposes.
        They must NEVER be processed as real candidates or affect scoring.
        """
        return [
            {
                "vessel_id": "TEST-VESSEL-01",
                "is_mock": True,
                "rank": 2,
                "score": None,
                "vessel_name": "Demo Cargo Ship Alpha",
                "mmsi": "000000001",
                "imo": "IMO0000001",
                "distance_to_origin_km": 12.5,
                "time_difference_hours": 1.2,
                "trajectory_correlation": 0.45
            },
            {
                "vessel_id": "TEST-VESSEL-02",
                "is_mock": True,
                "rank": 3,
                "score": None,
                "vessel_name": "Demo Tanker Beta",
                "mmsi": "000000002",
                "imo": "IMO0000002",
                "distance_to_origin_km": 15.3,
                "time_difference_hours": 2.5,
                "trajectory_correlation": 0.32
            },
            {
                "vessel_id": "TEST-VESSEL-03",
                "is_mock": True,
                "rank": 4,
                "score": None,
                "vessel_name": "Demo Fishing Vessel Gamma",
                "mmsi": "000000003",
                "imo": "IMO0000003",
                "distance_to_origin_km": 19.8,
                "time_difference_hours": -1.1,
                "trajectory_correlation": 0.21
            }
        ]
