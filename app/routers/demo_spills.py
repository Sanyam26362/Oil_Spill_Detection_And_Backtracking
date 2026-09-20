from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import math
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    CentroidSchema,
    DemoAttributionTrajectoryResponse,
    DemoBacktrackResponse,
    DemoPaginationResponse,
    DemoSpillDetail,
    DemoSpillListItem,
    DemoSpillVessel,
    DemoSpillVesselResponse,
    PredictedPosition,
    PredictionTrajectoryPoint,
    SpillPredictionResponse,
)
from app.models.ais import AISPosition
from app.repositories.ais_repository import AISRepository
from app.routers.attribution import get_attribution_engine
from app.routers.drift import get_drift_engine
from app.services.attribution_engine import AttributionEngine
from app.services.demo_vessel_evidence_service import (
    DemoVesselEvidenceService,
)
from app.services.drift_engine import DriftEngine
from app.services.maritime_simulation import snap_to_clean_30min
from app.services.mock_vessel_service import (
    ForensicSubScoreCalculator,
    MockVesselService,
    extract_vessel_seed,
    generate_valid_imo,
    generate_valid_mmsi,
)
from app.services.spill_catalog_service import SpillCatalogService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=DemoPaginationResponse)
async def list_spills(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
):
    skip = (page - 1) * page_size

    spills = SpillCatalogService.get_all_spills(skip=skip, limit=page_size)

    total = SpillCatalogService.get_total_count()

    items = []

    for s in spills:
        items.append(
            DemoSpillListItem(
                spill_id=s["spill_id"],
                detected_at=datetime.fromisoformat(s["detected_at"]),
                centroid=CentroidSchema(
                    lon=s["observation_longitude"],
                    lat=s["observation_latitude"],
                ),
                area_km2=s["area_km2"],
                confidence_score=s["confidence_score"],
                candidate_count=s["candidate_count"],
                image_url=s["image_reference"],
            )
        )

    return DemoPaginationResponse(
        total=total, page=page, page_size=page_size, items=items
    )


@router.get("/{spill_id}", response_model=DemoSpillDetail)
async def get_spill_detail(spill_id: str):
    s = SpillCatalogService.get_spill(spill_id)

    if not s:
        raise HTTPException(
            status_code=404, detail="Spill not found in demo catalog"
        )

    return DemoSpillDetail(
        spill_id=s["spill_id"],
        source_type=s["source_type"],
        source_file=s["source_file"],
        detected_at=datetime.fromisoformat(s["detected_at"]),
        estimated_age_hours=s["estimated_age_hours"],
        estimated_release_time=datetime.fromisoformat(
            s["estimated_release_time"]
        ),
        observation_latitude=s["observation_latitude"],
        observation_longitude=s["observation_longitude"],
        centroid=CentroidSchema(
            lon=s["observation_longitude"], lat=s["observation_latitude"]
        ),
        polygon=s["polygon"],
        area_km2=s["area_km2"],
        confidence_score=s["confidence_score"],
        image_url=s["image_reference"],
        estimated_source_latitude=s["estimated_source_latitude"],
        estimated_source_longitude=s["estimated_source_longitude"],
        estimated_source_radius_km=s["estimated_source_radius_km"],
        candidate_count=s["candidate_count"],
        ranked_top_vessel=s["ranked_top_vessel"],
        ranked_top_score=s["ranked_top_score"],
        runtime_seconds=s["runtime_seconds"],
    )


def _infer_shiptype_code(shiptype_name: str | None) -> int | None:
    if not shiptype_name:
        return None
    name_lower = shiptype_name.lower()
    if "passenger" in name_lower:
        return 60
    if "cargo" in name_lower:
        return 70
    if "tanker" in name_lower:
        return 80
    if "fishing" in name_lower:
        return 30
    if "tug" in name_lower:
        return 52
    if "pleasure" in name_lower:
        return 37
    return 90


async def _build_spill_vessels(
    spill_id: str,
    db: AsyncSession,
    prefetched_vessel: Any | None = None,
    prefetched_positions: list[AISPosition] | None = None,
) -> DemoSpillVesselResponse:
    s = SpillCatalogService.get_spill(spill_id)

    if not s:
        raise HTTPException(
            status_code=404, detail="Spill not found in demo catalog"
        )

    vessels = []

    # 1. Real top vessel
    real_vessel_id = s.get("ranked_top_vessel")
    if real_vessel_id:
        seed = extract_vessel_seed(real_vessel_id)

        top_score_val = s.get("ranked_top_score")
        if top_score_val is not None:
            derived_correlation = round(
                min(0.98, max(0.15, float(top_score_val) * 1.1)), 2
            )
        else:
            derived_correlation = round(min(0.98, max(0.15, 0.25 * 1.1)), 2)

        vessel_data = {
            "vessel_id": real_vessel_id,
            "vessel_name": real_vessel_id,
            "is_mock": False,
            "is_mock_comparison": False,
            "rank": 1,
            "score": top_score_val,
            "mmsi": generate_valid_mmsi("CY", seed, offset=0),
            "imo": generate_valid_imo(seed, offset=0),
            "country": "CY",
            "shiptype": 60,
            "shiptype_name": "Passenger",
            "vessel_type": "Passenger",
            "speed": None,
            "course": None,
            "heading": None,
            "distance_to_origin_km": None,
            "time_difference_hours": None,
            "trajectory_correlation": derived_correlation,
        }

        # Query database for actual vessel details and positions (read-only)
        session = db

        try:
            ais_repo = AISRepository()
            if prefetched_vessel is not None:
                vessel_meta = prefetched_vessel
            else:
                vessel_meta = await ais_repo.get_vessel(session, real_vessel_id)
            if vessel_meta:
                vessel_data["country"] = (
                    vessel_meta.country or vessel_data["country"]
                )
                vessel_data["shiptype_name"] = (
                    vessel_meta.shiptype_name or vessel_data["shiptype_name"]
                )
                vessel_data["vessel_type"] = (
                    vessel_meta.shiptype_name or vessel_data["vessel_type"]
                )
                if vessel_meta.shiptype is not None:
                    vessel_data["shiptype"] = vessel_meta.shiptype
                else:
                    vessel_data["shiptype"] = _infer_shiptype_code(
                        vessel_meta.shiptype_name
                    )

                # Set MMSI and IMO based on detected country and seed
                vessel_data["mmsi"] = generate_valid_mmsi(
                    vessel_meta.country, seed, offset=0
                )
                vessel_data["imo"] = generate_valid_imo(seed, offset=0)

            # Look up nearest AIS observation to the spill release origin
            rel_time_str = s.get("estimated_release_time")
            if rel_time_str:
                release_time = datetime.fromisoformat(rel_time_str)
                if release_time.tzinfo is None:
                    release_time = release_time.replace(tzinfo=timezone.utc)

                origin_lat = s.get("estimated_source_latitude") or s.get(
                    "observation_latitude"
                )
                origin_lon = s.get("estimated_source_longitude") or s.get(
                    "observation_longitude"
                )

                corridor_center = (
                    (origin_lat, origin_lon)
                    if origin_lat is not None and origin_lon is not None
                    else None
                )
                if prefetched_positions is not None:
                    positions = prefetched_positions
                else:
                    positions = await ais_repo.get_positions_for_vessel(
                        db=session,
                        vessel_id=real_vessel_id,
                        start_time=release_time - timedelta(hours=2),
                        end_time=release_time + timedelta(hours=2),
                        synthetic_only=True,
                        corridor_origin=corridor_center,
                        max_corridor_radius_km=120.0,
                    )
                if (
                    positions
                    and origin_lat is not None
                    and origin_lon is not None
                ):
                    closest = min(
                        positions,
                        key=lambda p: DriftEngine.haversine_km(
                            origin_lat,
                            origin_lon,
                            float(p.latitude),
                            float(p.longitude),
                        ),
                    )
                    dist = DriftEngine.haversine_km(
                        origin_lat,
                        origin_lon,
                        float(closest.latitude),
                        float(closest.longitude),
                    )
                    vessel_data["distance_to_origin_km"] = round(dist, 2)
                    vessel_data["speed"] = (
                        round(float(closest.speed), 2)
                        if closest.speed is not None
                        else None
                    )
                    vessel_data["course"] = (
                        round(float(closest.course), 2)
                        if closest.course is not None
                        else None
                    )
                    vessel_data["heading"] = (
                        round(float(closest.heading), 2)
                        if closest.heading is not None
                        else None
                    )

                    p_time = closest.timestamp
                    if p_time.tzinfo is None:
                        p_time = p_time.replace(tzinfo=timezone.utc)
                    vessel_data["time_difference_hours"] = round(
                        (p_time - release_time).total_seconds() / 3600.0, 2
                    )
        except Exception:
            # C2: log the exception so failures are visible in server logs.
            # Control flow is unchanged — the endpoint still returns the
            # un-enriched vessel data successfully.
            logger.exception(
                "DB enrichment failed for vessel %s (spill %s)",
                real_vessel_id,
                spill_id,
            )

        # Compute forensic sub-scores from the real vessel's AIS attributes.
        # This is always called so that sub-scores are never null for rank-1.
        # ForensicSubScoreCalculator is pure and does NOT alter rank or score.
        vessel_data.update(
            ForensicSubScoreCalculator.compute(
                distance_to_origin_km=vessel_data.get(
                    "distance_to_origin_km"
                ),
                time_difference_hours=vessel_data.get(
                    "time_difference_hours"
                ),
                speed=vessel_data.get("speed"),
                vessel_type=vessel_data.get("vessel_type"),
                mock_index=0,
            )
        )
        # Restore the real attribution score produced by the engine;
        # ForensicSubScoreCalculator.compute() writes "score" as well,
        # but for rank-1 the catalog score must take precedence.
        if top_score_val is not None:
            vessel_data["score"] = top_score_val

        vessels.append(DemoSpillVessel(**vessel_data))

    # 2. Mock vessels
    real_vessel = vessels[0] if vessels else None
    mock_vessels = MockVesselService.get_mock_vessels(
        base_vessel_id=real_vessel_id,
        real_vessel=real_vessel,
    )
    for mv in mock_vessels:
        vessels.append(DemoSpillVessel(**mv))

    return DemoSpillVesselResponse(spill_id=spill_id, vessels=vessels)


@router.get("/{spill_id}/vessels", response_model=DemoSpillVesselResponse)
async def get_spill_vessels(
    spill_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await _build_spill_vessels(spill_id, db=db)


# ============================================================
# NEW API
# ============================================================

@router.get(
    "/{spill_id}/attribution/trajectory",
    response_model=DemoAttributionTrajectoryResponse,
)
async def get_spill_attribution_trajectory(
    spill_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return attribution evidence and vessel trajectories.

    IMPORTANT:
    The vessel list comes from the existing /vessels endpoint,
    so this endpoint cannot produce a different culprit list.
    """

    s = SpillCatalogService.get_spill(spill_id)

    if not s:
        raise HTTPException(
            status_code=404, detail="Spill not found in demo catalog"
        )

    try:
        # E3: Consolidate redundant DB queries into a single widest-window
        # get_positions_for_vessel call plus one get_vessel call.
        real_vessel_id = s.get("ranked_top_vessel")
        vessel_metadata = None
        widest_positions = None
        sliced_vessels_positions = None

        if real_vessel_id:
            ais_repo = AISRepository()
            rel_time_str = s.get("estimated_release_time")
            if rel_time_str:
                release_time = datetime.fromisoformat(rel_time_str)
                if release_time.tzinfo is None:
                    release_time = release_time.replace(tzinfo=timezone.utc)

                detected_at_str = s.get("detected_at")
                detected_at = (
                    datetime.fromisoformat(detected_at_str)
                    if detected_at_str
                    else None
                )
                if detected_at and detected_at.tzinfo is None:
                    detected_at = detected_at.replace(tzinfo=timezone.utc)

                origin_lat = s.get("estimated_source_latitude") or s.get(
                    "observation_latitude"
                )
                origin_lon = s.get("estimated_source_longitude") or s.get(
                    "observation_longitude"
                )
                corridor_center = (
                    (origin_lat, origin_lon)
                    if origin_lat is not None and origin_lon is not None
                    else None
                )

                nominal_start = release_time - timedelta(hours=3)
                start_time = snap_to_clean_30min(nominal_start, "round")

                if detected_at is not None:
                    nominal_end = detected_at + timedelta(hours=3)
                    end_time = snap_to_clean_30min(nominal_end, "round")
                else:
                    nominal_end = release_time + timedelta(hours=6)
                    end_time = snap_to_clean_30min(nominal_end, "round")

                if end_time < start_time + timedelta(hours=6):
                    end_time = start_time + timedelta(hours=6)

                duration_hours = (
                    end_time - start_time
                ).total_seconds() / 3600.0
                dynamic_corridor_km = min(
                    600.0, max(150.0, 120.0 + duration_hours * 25.0)
                )

                widest_start = min(
                    start_time, release_time - timedelta(hours=2)
                )
                widest_end = max(
                    end_time, release_time + timedelta(hours=2)
                )
                widest_corridor_km = max(dynamic_corridor_km, 120.0)

                vessel_metadata = await ais_repo.get_vessel(db, real_vessel_id)
                widest_positions = await ais_repo.get_positions_for_vessel(
                    db=db,
                    vessel_id=real_vessel_id,
                    start_time=widest_start,
                    end_time=widest_end,
                    synthetic_only=True,
                    corridor_origin=corridor_center,
                    max_corridor_radius_km=widest_corridor_km,
                )

                vessels_start = release_time - timedelta(hours=2)
                vessels_end = release_time + timedelta(hours=2)
                sliced_vessels_positions = [
                    p
                    for p in widest_positions
                    if vessels_start <= p.timestamp <= vessels_end
                    and (
                        corridor_center is None
                        or ais_repo._haversine_distance_m(
                            origin_lat, origin_lon, p.latitude, p.longitude
                        )
                        <= 120.0 * 1000.0
                    )
                ]

        existing_vessel_response = await _build_spill_vessels(
            spill_id,
            db=db,
            prefetched_vessel=vessel_metadata,
            prefetched_positions=sliced_vessels_positions,
        )

        service = DemoVesselEvidenceService()

        return await service.build(
            db=db,
            spill=s,
            vessels=existing_vessel_response.vessels,
            prefetched_vessel=vessel_metadata,
            prefetched_widest_positions=widest_positions,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "Error building attribution trajectory for %s", spill_id
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Internal server error while "
                "building attribution trajectory"
            ),
        ) from exc


@router.post(
    "/{spill_id}/backtrack",
    response_model=DemoBacktrackResponse,
)
async def backtrack_spill(
    spill_id: str,
    db: AsyncSession = Depends(get_db),
    engine: AttributionEngine = Depends(get_attribution_engine),
):
    s = SpillCatalogService.get_spill(spill_id)

    if not s:
        raise HTTPException(
            status_code=404, detail="Spill not found in demo catalog"
        )
    spill = s

    try:
        dt = datetime.fromisoformat(s["detected_at"])

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        started = time.perf_counter()

        result = await engine.attribute(
            db=db,
            observation_latitude=s["observation_latitude"],
            observation_longitude=s["observation_longitude"],
            observation_time=dt,
            drift_duration_hours=s["estimated_age_hours"],
            ensemble_size=100,
            initial_radius_m=500.0,
            timestep_minutes=15,
            candidate_radius_margin_km=5.0,
            candidate_time_window_hours=2.0,
            synthetic_only=True,
            scenario_id=None,
        )

        elapsed = time.perf_counter() - started

        logger.info(
            "spill_id=%s backtrack_runtime_seconds=%.3f",
            spill_id,
            elapsed,
        )

        source_estimate = result.get("source_estimate") or {}

        # Build backtrack object
        backtrack_obj = {
            "observation": {
                "latitude": s["observation_latitude"],
                "longitude": s["observation_longitude"],
                "timestamp": s["detected_at"],
            },
            "estimated_release_time": result.get("estimated_release_time"),
            "source_estimate": {
                "latitude": source_estimate.get("latitude"),
                "longitude": source_estimate.get("longitude"),
                "radius_km": source_estimate.get("radius_km"),
            },
        }

        # Safely extract top candidate and score
        candidates = result.get("candidates", [])
        if candidates:
            top_cand = candidates[0]
            top_vessel = top_cand.get("vessel_id")
            top_score = top_cand.get("score")
            candidate_count = len(candidates)
            SpillCatalogService.update_spill_attribution(
                spill_id=spill_id,
                top_vessel=top_vessel,
                top_score=top_score,
                candidate_count=candidate_count,
            )

        top_cand = candidates[0] if candidates else {}
        top_score = top_cand.get("score")
        # F8: Remove dead top_cand.get("total_score") fallback —
        # candidate dicts only ever carry "score".
        if top_score is None and spill.get("ranked_top_score") is not None:
            try:
                top_score = float(spill["ranked_top_score"])
            except (ValueError, TypeError):
                top_score = None

        # Build attribution object
        attribution_obj = {
            "candidate_count": result.get("candidate_count", 0),
            "top_vessel": result.get("top_prediction"),
            "top_score": top_score,
        }

        return DemoBacktrackResponse(
            spill_id=spill_id,
            backtrack=backtrack_obj,
            attribution=attribution_obj,
        )

    except Exception as exc:
        logger.exception("Error during backtrack for %s", spill_id)

        raise HTTPException(
            status_code=500,
            detail=(
                "Internal server error during "
                "backtrack calculation"
            ),
        ) from exc


# ============================================================
# FORWARD DRIFT PREDICTION API
# ============================================================

@router.get(
    "/{spill_id}/predict",
    response_model=SpillPredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict forward position and trajectory for a demo spill",
)
@router.get(
    "/predict/{spill_id}",
    response_model=SpillPredictionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def predict_demo_spill_trajectory(
    spill_id: str,
    hours: float = Query(
        6.0, gt=0, le=72.0, description="Hours to predict forward (default 6.0)"
    ),
    timestep_minutes: int = Query(
        15, ge=1, le=120, description="Minutes between waypoints (default 15)"
    ),
    drift_engine: DriftEngine = Depends(get_drift_engine),
):
    """
    Retrieve spill detection coordinates and timestamp from the demo catalog,
    run the forward drift physics simulation for the requested time window,
    and output the projected final position, net displacement, heading,
    and trajectory path.
    """
    s = SpillCatalogService.get_spill(spill_id)

    if not s:
        raise HTTPException(
            status_code=404,
            detail=f"Spill '{spill_id}' not found in demo catalog",
        )

    start_lat = float(s["observation_latitude"])
    start_lon = float(s["observation_longitude"])
    detected_at_raw = s["detected_at"]

    start_time = datetime.fromisoformat(detected_at_raw)
    if start_time.tzinfo is not None:
        start_time_naive = start_time.replace(tzinfo=None)
    else:
        start_time_naive = start_time

    try:
        # D3: wrap blocking physics in threadpool
        drift_trajectory = await run_in_threadpool(
            drift_engine.forward_drift,
            start_latitude=start_lat,
            start_longitude=start_lon,
            start_time=start_time_naive,
            duration_hours=hours,
            timestep_minutes=timestep_minutes,
        )

        states = drift_trajectory.states
        if not states:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Metocean velocity unavailable for spill '{spill_id}' at time {detected_at_raw}.",
            )

        trajectory_points: list[PredictionTrajectoryPoint] = []
        speed_records_knots: list[float] = []

        for state in states:
            u = state.drift_u
            v = state.drift_v
            speed_mps = float(math.hypot(u, v))
            speed_knots = float(speed_mps * 1.94384)
            speed_records_knots.append(speed_knots)

            heading_deg = float(
                (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
            )
            dist_km = float(
                DriftEngine.haversine_km(
                    start_lat, start_lon, state.latitude, state.longitude
                )
            )

            trajectory_points.append(
                PredictionTrajectoryPoint(
                    timestamp=state.timestamp,
                    latitude=round(float(state.latitude), 6),
                    longitude=round(float(state.longitude), 6),
                    drift_speed_knots=round(speed_knots, 2),
                    drift_heading_deg=round(heading_deg, 1),
                    distance_from_start_km=round(dist_km, 3),
                )
            )

        final_state = states[-1]
        final_lat = float(final_state.latitude)
        final_lon = float(final_state.longitude)

        total_disp = float(
            DriftEngine.haversine_km(
                start_lat, start_lon, final_lat, final_lon
            )
        )

        # Net bearing from initial observation to projected final position
        d_lon = math.radians(final_lon - start_lon)
        lat1_rad = math.radians(start_lat)
        lat2_rad = math.radians(final_lat)
        y = math.sin(d_lon) * math.cos(lat2_rad)
        x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(
            lat1_rad
        ) * math.cos(lat2_rad) * math.cos(d_lon)
        net_bearing = float((math.degrees(math.atan2(y, x)) + 360.0) % 360.0)

        avg_speed = (
            float(np.mean(speed_records_knots)) if speed_records_knots else 0.0
        )

        return SpillPredictionResponse(
            spill_id=spill_id,
            forecast_hours=hours,
            initial_position=PredictedPosition(
                latitude=round(start_lat, 6),
                longitude=round(start_lon, 6),
                timestamp=start_time,
            ),
            predicted_position=PredictedPosition(
                latitude=round(final_lat, 6),
                longitude=round(final_lon, 6),
                timestamp=final_state.timestamp,
            ),
            total_displacement_km=round(total_disp, 3),
            net_heading_deg=round(net_bearing, 1),
            average_speed_knots=round(avg_speed, 2),
            trajectory=trajectory_points,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during forward prediction for %s", spill_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forward drift prediction failed: {str(exc)}",
        ) from exc