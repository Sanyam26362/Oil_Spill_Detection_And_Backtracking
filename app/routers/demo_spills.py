from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta
import time
import re

from app.core.database import get_db, AsyncSessionLocal
from app.repositories.ais_repository import AISRepository
from app.services.drift_engine import DriftEngine

from app.models.schemas import (
    DemoPaginationResponse,
    DemoSpillListItem,
    DemoSpillDetail,
    DemoSpillVessel,
    DemoSpillVesselResponse,
    DemoBacktrackResponse,
    CentroidSchema,
    DemoAttributionTrajectoryResponse,
)

from app.services.spill_catalog_service import SpillCatalogService
from app.services.mock_vessel_service import (
    MockVesselService,
    generate_valid_mmsi,
    generate_valid_imo,
    extract_vessel_seed,
)
from app.routers.attribution import get_attribution_engine
from app.services.attribution_engine import AttributionEngine
from app.services.demo_vessel_evidence_service import (
    DemoVesselEvidenceService,
)


router = APIRouter()


@router.get(
    "",
    response_model=DemoPaginationResponse
)
async def list_spills(
    page: int = Query(1, ge=1),
    page_size: int = Query(
        20,
        ge=1,
        le=100
    )
):
    skip = (page - 1) * page_size

    spills = SpillCatalogService.get_all_spills(
        skip=skip,
        limit=page_size
    )

    total = SpillCatalogService.get_total_count()

    items = []

    for s in spills:
        items.append(
            DemoSpillListItem(
                spill_id=s["spill_id"],
                detected_at=datetime.fromisoformat(
                    s["detected_at"]
                ),
                centroid=CentroidSchema(
                    lon=s["observation_longitude"],
                    lat=s["observation_latitude"]
                ),
                area_km2=s["area_km2"],
                confidence_score=s["confidence_score"],
                candidate_count=s["candidate_count"],
                image_url=s["image_reference"]
            )
        )

    return DemoPaginationResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )


@router.get(
    "/{spill_id}",
    response_model=DemoSpillDetail
)
async def get_spill_detail(
    spill_id: str
):
    s = SpillCatalogService.get_spill(
        spill_id
    )

    if not s:
        raise HTTPException(
            status_code=404,
            detail="Spill not found in demo catalog"
        )

    return DemoSpillDetail(
        spill_id=s["spill_id"],
        source_type=s["source_type"],
        source_file=s["source_file"],
        detected_at=datetime.fromisoformat(
            s["detected_at"]
        ),
        estimated_age_hours=s[
            "estimated_age_hours"
        ],
        estimated_release_time=datetime.fromisoformat(
            s["estimated_release_time"]
        ),
        observation_latitude=s[
            "observation_latitude"
        ],
        observation_longitude=s[
            "observation_longitude"
        ],
        centroid=CentroidSchema(
            lon=s["observation_longitude"],
            lat=s["observation_latitude"]
        ),
        polygon=s["polygon"],
        area_km2=s["area_km2"],
        confidence_score=s[
            "confidence_score"
        ],
        image_url=s["image_reference"],
        estimated_source_latitude=s[
            "estimated_source_latitude"
        ],
        estimated_source_longitude=s[
            "estimated_source_longitude"
        ],
        estimated_source_radius_km=s[
            "estimated_source_radius_km"
        ],
        candidate_count=s[
            "candidate_count"
        ],
        ranked_top_vessel=s[
            "ranked_top_vessel"
        ],
        ranked_top_score=s[
            "ranked_top_score"
        ],
        runtime_seconds=s[
            "runtime_seconds"
        ]
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


@router.get(
    "/{spill_id}/vessels",
    response_model=DemoSpillVesselResponse
)
async def get_spill_vessels(
    spill_id: str,
    db: AsyncSession | None = Depends(get_db),
):
    s = SpillCatalogService.get_spill(
        spill_id
    )

    if not s:
        raise HTTPException(
            status_code=404,
            detail="Spill not found in demo catalog"
        )

    vessels = []

    # 1. Real top vessel
    real_vessel_id = s.get("ranked_top_vessel")
    if real_vessel_id:
        seed = extract_vessel_seed(real_vessel_id)

        top_score_val = s.get("ranked_top_score")
        if top_score_val is not None:
            derived_correlation = round(min(0.98, max(0.15, float(top_score_val) * 1.1)), 2)
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
        close_session = False
        if session is None:
            session = AsyncSessionLocal()
            close_session = True

        try:
            ais_repo = AISRepository()
            vessel_meta = await ais_repo.get_vessel(session, real_vessel_id)
            if vessel_meta:
                vessel_data["country"] = vessel_meta.country or vessel_data["country"]
                vessel_data["shiptype_name"] = vessel_meta.shiptype_name or vessel_data["shiptype_name"]
                vessel_data["vessel_type"] = vessel_meta.shiptype_name or vessel_data["vessel_type"]
                if vessel_meta.shiptype is not None:
                    vessel_data["shiptype"] = vessel_meta.shiptype
                else:
                    vessel_data["shiptype"] = _infer_shiptype_code(vessel_meta.shiptype_name)

                # Set MMSI and IMO based on detected country and seed
                vessel_data["mmsi"] = generate_valid_mmsi(vessel_meta.country, seed, offset=0)
                vessel_data["imo"] = generate_valid_imo(seed, offset=0)

            # Look up nearest AIS observation to the spill release origin
            rel_time_str = s.get("estimated_release_time")
            if rel_time_str:
                release_time = datetime.fromisoformat(rel_time_str)
                if release_time.tzinfo is None:
                    release_time = release_time.replace(tzinfo=timezone.utc)

                origin_lat = s.get("estimated_source_latitude") or s.get("observation_latitude")
                origin_lon = s.get("estimated_source_longitude") or s.get("observation_longitude")

                corridor_center = (origin_lat, origin_lon) if origin_lat is not None and origin_lon is not None else None
                positions = await ais_repo.get_positions_for_vessel(
                    db=session,
                    vessel_id=real_vessel_id,
                    start_time=release_time - timedelta(hours=2),
                    end_time=release_time + timedelta(hours=2),
                    synthetic_only=True,
                    corridor_origin=corridor_center,
                    max_corridor_radius_km=120.0,
                )
                if positions and origin_lat is not None and origin_lon is not None:
                    closest = min(
                        positions,
                        key=lambda p: DriftEngine.haversine_km(
                            origin_lat, origin_lon, float(p.latitude), float(p.longitude)
                        )
                    )
                    dist = DriftEngine.haversine_km(
                        origin_lat, origin_lon, float(closest.latitude), float(closest.longitude)
                    )
                    vessel_data["distance_to_origin_km"] = round(dist, 2)
                    vessel_data["speed"] = round(float(closest.speed), 2) if closest.speed is not None else None
                    vessel_data["course"] = round(float(closest.course), 2) if closest.course is not None else None
                    vessel_data["heading"] = round(float(closest.heading), 2) if closest.heading is not None else None

                    p_time = closest.timestamp
                    if p_time.tzinfo is None:
                        p_time = p_time.replace(tzinfo=timezone.utc)
                    vessel_data["time_difference_hours"] = round((p_time - release_time).total_seconds() / 3600.0, 2)
        except Exception:
            pass
        finally:
            if close_session:
                await session.close()

        vessels.append(DemoSpillVessel(**vessel_data))

    # 2. Mock vessels
    real_vessel = vessels[0] if vessels else None
    mock_vessels = MockVesselService.get_mock_vessels(
        base_vessel_id=real_vessel_id,
        real_vessel=real_vessel,
    )
    for mv in mock_vessels:
        vessels.append(DemoSpillVessel(**mv))

    return DemoSpillVesselResponse(
        spill_id=spill_id,
        vessels=vessels
    )


# ============================================================
# NEW API
# ============================================================

@router.get(
    "/{spill_id}/attribution/trajectory",
    response_model=DemoAttributionTrajectoryResponse
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

    s = SpillCatalogService.get_spill(
        spill_id
    )

    if not s:
        raise HTTPException(
            status_code=404,
            detail="Spill not found in demo catalog"
        )

    try:
        # --------------------------------------------------------
        # Reuse the EXISTING /vessels endpoint.
        #
        # This guarantees:
        #
        #   rank 1 -> real culprit
        #   rank 2 -> mock vessel 1
        #   rank 3 -> mock vessel 2
        #   rank 4 -> mock vessel 3
        # --------------------------------------------------------

        existing_vessel_response = (
            await get_spill_vessels(
                spill_id,
                db=db,
            )
        )

        service = (
            DemoVesselEvidenceService()
        )

        return await service.build(
            db=db,
            spill=s,
            vessels=existing_vessel_response.vessels,
        )

    except HTTPException:
        raise

    except Exception as exc:
        print(
            "Error building attribution "
            f"trajectory for {spill_id}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Internal server error while "
                "building attribution trajectory"
            )
        ) from exc


@router.post(
    "/{spill_id}/backtrack",
    response_model=DemoBacktrackResponse
)
async def backtrack_spill(
    spill_id: str,
    db: AsyncSession = Depends(get_db),
    engine: AttributionEngine = Depends(
        get_attribution_engine
    )
):
    s = SpillCatalogService.get_spill(
        spill_id
    )

    if not s:
        raise HTTPException(
            status_code=404,
            detail="Spill not found in demo catalog"
        )
    spill = s

    try:
        dt = datetime.fromisoformat(
            s["detected_at"]
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        started = time.perf_counter()

        result = await engine.attribute(
            db=db,
            observation_latitude=s[
                "observation_latitude"
            ],
            observation_longitude=s[
                "observation_longitude"
            ],
            observation_time=dt,
            drift_duration_hours=s[
                "estimated_age_hours"
            ],
            ensemble_size=100,
            initial_radius_m=500.0,
            timestep_minutes=15,
            candidate_radius_margin_km=5.0,
            candidate_time_window_hours=2.0,
            synthetic_only=True,
            scenario_id=None
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        print(
            f"spill_id={spill_id} "
            f"backtrack_runtime_seconds="
            f"{elapsed:.3f}"
        )

        source_estimate = (
            result.get("source_estimate")
            or {}
        )

        # Build backtrack object
        backtrack_obj = {
            "observation": {
                "latitude": s[
                    "observation_latitude"
                ],
                "longitude": s[
                    "observation_longitude"
                ],
                "timestamp": s[
                    "detected_at"
                ]
            },
            "estimated_release_time":
                result.get(
                    "estimated_release_time"
                ),
            "source_estimate": {
                "latitude":
                    source_estimate.get(
                        "latitude"
                    ),
                "longitude":
                    source_estimate.get(
                        "longitude"
                    ),
                "radius_km":
                    source_estimate.get(
                        "radius_km"
                    )
            }
        }

        # Safely extract top candidate and score
        candidates = result.get(
            "candidates",
            []
        )
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
        if top_score is None:
            top_score = top_cand.get("total_score")
        if top_score is None and spill.get("ranked_top_score") is not None:
            try:
                top_score = float(spill["ranked_top_score"])
            except (ValueError, TypeError):
                top_score = None

        # Build attribution object
        attribution_obj = {
            "candidate_count":
                result.get(
                    "candidate_count",
                    0
                ),
            "top_vessel":
                result.get(
                    "top_prediction"
                ),
            "top_score": top_score
        }

        return DemoBacktrackResponse(
            spill_id=spill_id,
            backtrack=backtrack_obj,
            attribution=attribution_obj
        )

    except Exception as exc:
        print(
            f"Error during backtrack "
            f"for {spill_id}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Internal server error during "
                "backtrack calculation"
            )
        ) from exc