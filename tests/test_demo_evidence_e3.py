import pytest
from datetime import datetime, timezone, timedelta
from app.core.database import AsyncSessionLocal
from app.repositories.ais_repository import AISRepository
from app.services.spill_catalog_service import SpillCatalogService
from app.services.maritime_simulation import snap_to_clean_30min

@pytest.mark.asyncio
async def test_sliced_in_memory_matches_separate_queries():
    SpillCatalogService.initialize()
    spill = SpillCatalogService.get_spill("spill_4e354b")
    assert spill is not None, "spill_4e354b should exist in catalog"

    real_vessel_id = spill.get("ranked_top_vessel")
    assert real_vessel_id is not None

    try:
        async with AsyncSessionLocal() as session:
            await AISRepository.get_vessel(session, real_vessel_id)
    except Exception:
        pytest.skip("Database not available for AIS queries")

    rel_time_str = spill.get("estimated_release_time")
    release_time = datetime.fromisoformat(rel_time_str)
    if release_time.tzinfo is None:
        release_time = release_time.replace(tzinfo=timezone.utc)

    detected_at_str = spill.get("detected_at")
    detected_at = datetime.fromisoformat(detected_at_str) if detected_at_str else None
    if detected_at and detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)

    origin_lat = spill.get("estimated_source_latitude") or spill.get("observation_latitude")
    origin_lon = spill.get("estimated_source_longitude") or spill.get("observation_longitude")
    corridor_center = (origin_lat, origin_lon) if origin_lat and origin_lon else None

    # Window 1: get_spill_vessels window
    vessels_start = release_time - timedelta(hours=2)
    vessels_end = release_time + timedelta(hours=2)

    # Window 2: attrib_positions window
    attrib_start = release_time - timedelta(hours=2)
    attrib_end = release_time + timedelta(hours=2)

    # Window 3: real_positions window
    nominal_start = release_time - timedelta(hours=3)
    real_start = snap_to_clean_30min(nominal_start, "round")
    if detected_at:
        real_end = snap_to_clean_30min(detected_at + timedelta(hours=3), "round")
    else:
        real_end = snap_to_clean_30min(release_time + timedelta(hours=6), "round")
    if real_end < real_start + timedelta(hours=6):
        real_end = real_start + timedelta(hours=6)

    duration_hours = (real_end - real_start).total_seconds() / 3600.0
    dynamic_corridor_km = min(600.0, max(150.0, 120.0 + duration_hours * 25.0))

    ais_repo = AISRepository()
    async with AsyncSessionLocal() as session:
        # Separate old queries
        vessel_meta_old = await ais_repo.get_vessel(session, real_vessel_id)
        pos_vessels_old = await ais_repo.get_positions_for_vessel(
            session, real_vessel_id, vessels_start, vessels_end,
            synthetic_only=True, corridor_origin=corridor_center, max_corridor_radius_km=120.0
        )
        pos_attrib_old = await ais_repo.get_positions_for_vessel(
            session, real_vessel_id, attrib_start, attrib_end,
            synthetic_only=True, corridor_origin=corridor_center, max_corridor_radius_km=120.0
        )
        pos_real_old = await ais_repo.get_positions_for_vessel(
            session, real_vessel_id, real_start, real_end,
            synthetic_only=True, corridor_origin=corridor_center, max_corridor_radius_km=dynamic_corridor_km
        )

        # Single consolidated widest-window query
        widest_start = min(real_start, vessels_start, attrib_start)
        widest_end = max(real_end, vessels_end, attrib_end)
        widest_corridor_km = max(dynamic_corridor_km, 120.0)

        vessel_meta_new = await ais_repo.get_vessel(session, real_vessel_id)
        widest_positions = await ais_repo.get_positions_for_vessel(
            session, real_vessel_id, widest_start, widest_end,
            synthetic_only=True, corridor_origin=corridor_center, max_corridor_radius_km=widest_corridor_km
        )

        # In-memory slicing
        pos_real_sliced = [p for p in widest_positions if real_start <= p.timestamp <= real_end]

        pos_attrib_sliced = [
            p for p in widest_positions
            if attrib_start <= p.timestamp <= attrib_end
            and (
                corridor_center is None
                or ais_repo._haversine_distance_m(origin_lat, origin_lon, p.latitude, p.longitude) <= 120.0 * 1000.0
            )
        ]

        pos_vessels_sliced = pos_attrib_sliced

        # Assert equality of metadata
        assert vessel_meta_old.vessel_id == vessel_meta_new.vessel_id
        assert vessel_meta_old.country == vessel_meta_new.country

        # Assert equality of position lists
        assert [p.id for p in pos_vessels_old] == [p.id for p in pos_vessels_sliced]
        assert [p.id for p in pos_attrib_old] == [p.id for p in pos_attrib_sliced]
        assert [p.id for p in pos_real_old] == [p.id for p in pos_real_sliced]

        assert len(pos_vessels_sliced) > 0
        assert len(pos_real_sliced) > 0
