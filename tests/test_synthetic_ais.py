"""Tests for synthetic AIS generation."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from scripts.synthetic.scenario import SyntheticScenarioConfig
from scripts.synthetic.generate_synthetic_ais import (
    generate_scenario_dataset,
    haversine_km,
    iso_utc,
)


def _make_test_config(seed=42):
    """Create a minimal test scenario config."""
    return SyntheticScenarioConfig(
        scenario_id="TEST-001",
        release_lat=33.5,
        release_lon=34.0,
        release_time=datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc),
        observation_lat=33.48,
        observation_lon=34.04,
        observation_time=datetime(2019, 7, 15, 18, 0, 0, tzinfo=timezone.utc),
        drift_duration_hours=6.0,
        bounds_lat_min=33.0,
        bounds_lat_max=34.0,
        bounds_lon_min=33.5,
        bounds_lon_max=34.5,
        num_background_vessels=10,
        num_decoy_vessels=4,
        vessel_id_prefix="SYNTH-TEST-",
        source_vessel_id="SYNTH-TEST-SRC",
        decoy_start_id=1,
        seed=seed,
    )


class TestTimestamps:
    """Test timestamp validity."""

    def test_clean_utc_strings(self):
        """All timestamps should be valid ISO UTC strings ending in Z."""
        config = _make_test_config()
        df, _ = generate_scenario_dataset(config)
        for ts in df["timestamp"]:
            assert ts.endswith("Z"), f"Timestamp does not end in Z: {ts}"
            assert "+00:00Z" not in ts, f"Double timezone suffix: {ts}"
            # Should parse without error
            parsed = pd.Timestamp(ts)
            assert parsed is not None

    def test_no_duplicate_vessel_timestamp(self):
        """No vessel should have duplicate timestamps."""
        config = _make_test_config()
        df, _ = generate_scenario_dataset(config)
        dupes = df.duplicated(subset=["vessel_id", "timestamp"], keep=False)
        assert not dupes.any(), f"Found duplicate vessel+timestamp records"


class TestSourceVessel:
    """Test source vessel behavior."""

    def test_source_vessel_has_release_record(self):
        """Source vessel must have a record at exact release time."""
        config = _make_test_config()
        df, gt = generate_scenario_dataset(config)
        source_id = gt["source"]["vessel_id"]
        release_ts = gt["source"]["timestamp"]
        source_records = df[df["vessel_id"] == source_id]
        assert release_ts in source_records["timestamp"].values, (
            f"Source vessel {source_id} missing release record at {release_ts}"
        )

    def test_source_vessel_near_source_at_release(self):
        """Source vessel should be near the release location at release time."""
        config = _make_test_config()
        df, gt = generate_scenario_dataset(config)
        source_id = gt["source"]["vessel_id"]
        release_ts = gt["source"]["timestamp"]
        record = df[
            (df["vessel_id"] == source_id) &
            (df["timestamp"] == release_ts)
        ]
        assert len(record) == 1
        dist = haversine_km(
            config.release_lat, config.release_lon,
            record.iloc[0]["latitude"], record.iloc[0]["longitude"],
        )
        assert dist < 0.1, f"Source vessel {dist:.4f} km from source at release"


class TestVesselIds:
    """Test globally unique vessel IDs."""

    def test_all_ids_have_prefix(self):
        """All vessel IDs should start with the scenario prefix."""
        config = _make_test_config()
        df, _ = generate_scenario_dataset(config)
        for vid in df["vessel_id"].unique():
            assert vid.startswith("SYNTH-TEST-"), f"ID missing prefix: {vid}"

    def test_ids_unique_across_scenarios(self):
        """Two scenarios with different prefixes should have disjoint IDs."""
        config1 = _make_test_config(seed=42)
        config1.vessel_id_prefix = "SYNTH-S001-"
        config1.source_vessel_id = "SYNTH-S001-SRC"
        config1.scenario_id = "S001"

        config2 = _make_test_config(seed=43)
        config2.vessel_id_prefix = "SYNTH-S002-"
        config2.source_vessel_id = "SYNTH-S002-SRC"
        config2.scenario_id = "S002"

        df1, _ = generate_scenario_dataset(config1)
        df2, _ = generate_scenario_dataset(config2)

        ids1 = set(df1["vessel_id"].unique())
        ids2 = set(df2["vessel_id"].unique())

        overlap = ids1 & ids2
        assert not overlap, f"Overlapping vessel IDs: {overlap}"


class TestScenarioId:
    """Test scenario_id presence."""

    def test_all_records_have_scenario_id(self):
        config = _make_test_config()
        df, _ = generate_scenario_dataset(config)
        assert (df["scenario_id"] == "TEST-001").all()

    def test_all_records_are_synthetic(self):
        config = _make_test_config()
        df, _ = generate_scenario_dataset(config)
        assert df["is_synthetic"].all()


class TestGeographicBounds:
    """Test that generated positions are geographically reasonable."""

    def test_no_teleportation(self):
        """Check for unrealistic jumps between consecutive records."""
        config = _make_test_config()
        df, _ = generate_scenario_dataset(config)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        max_jump_km = 0
        for vid in df["vessel_id"].unique():
            if "-DCY" in vid:
                continue
            
            vessel = df[df["vessel_id"] == vid].sort_values("timestamp")
            if len(vessel) < 2:
                continue
            for i in range(1, len(vessel)):
                dt = (vessel.iloc[i]["timestamp"] - vessel.iloc[i-1]["timestamp"]).total_seconds()
                if dt <= 0:
                    continue
                dist = haversine_km(
                    vessel.iloc[i-1]["latitude"], vessel.iloc[i-1]["longitude"],
                    vessel.iloc[i]["latitude"], vessel.iloc[i]["longitude"],
                )
                # Max plausible: 30 knots = ~55 km/h
                max_possible = 55.0 * dt / 3600.0 + 1.0
                if dist > max_jump_km:
                    max_jump_km = dist
                assert dist <= max_possible, (
                    f"Teleportation: {vid} moved {dist:.2f}km in {dt:.0f}s "
                    f"(max plausible {max_possible:.2f}km)"
                )


class TestGroundTruth:
    """Test ground truth structure."""

    def test_ground_truth_has_required_fields(self):
        config = _make_test_config()
        _, gt = generate_scenario_dataset(config)
        assert "scenario_id" in gt
        assert "source" in gt
        assert "observation" in gt
        assert "vessel_id" in gt["source"]
        assert "latitude" in gt["source"]
        assert "longitude" in gt["source"]
        assert "timestamp" in gt["source"]
