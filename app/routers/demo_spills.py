from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import time

from app.core.database import get_db

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
from app.services.mock_vessel_service import MockVesselService
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


@router.get(
    "/{spill_id}/vessels",
    response_model=DemoSpillVesselResponse
)
async def get_spill_vessels(
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

    vessels = []

    # 1. Real top vessel
    if s["ranked_top_vessel"]:
        vessels.append(
            DemoSpillVessel(
                vessel_id=s[
                    "ranked_top_vessel"
                ],
                is_mock=False,
                rank=1,
                score=s[
                    "ranked_top_score"
                ]
            )
        )

    # 2. Mock vessels
    mock_vessels = (
        MockVesselService.get_mock_vessels()
    )

    for mv in mock_vessels:
        vessels.append(
            DemoSpillVessel(**mv)
        )

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
        #   rank 2 -> TEST-VESSEL-01
        #   rank 3 -> TEST-VESSEL-02
        #   rank 4 -> TEST-VESSEL-03
        # --------------------------------------------------------

        existing_vessel_response = (
            await get_spill_vessels(
                spill_id
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
            "top_score": None
        }

        candidates = result.get(
            "candidates",
            []
        )

        if candidates:
            attribution_obj[
                "top_score"
            ] = candidates[
                0
            ].get(
                "total_score"
            )

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