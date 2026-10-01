"""
Lake feature extraction endpoints.

POST /lake-features/generate     — start computing ecological features (background task)
GET  /lake-features/status       — poll feature generation progress
POST /lake-features/generate-b8  — start fetching B8 (NIR) zonal stats (background task)
GET  /lake-features/status-b8    — poll B8 feature generation progress
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.dependencies import DatabaseDep
from app.core.permissions import require_pipeline_permission
from app.services.lake_feature_generator import (
    generate_lake_features,
    get_feature_progress,
)
from app.services.b8_feature_generator import (
    generate_b8_features,
    get_b8_feature_progress,
)
from app.schemas.lake_features import (
    GenerateLakeFeaturesRequest,
    GenerateLakeFeaturesResponse,
    LakeFeatureProgressResponse,
)

router = APIRouter(tags=["Lake Features"])
logger = structlog.get_logger(__name__)


@router.post("/generate", response_model=GenerateLakeFeaturesResponse)
async def generate_features(
    body: GenerateLakeFeaturesRequest,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_pipeline_permission("generate_features")),
) -> GenerateLakeFeaturesResponse:
    """
    Start computing ecological features from merged Sentinel-2 images.

    Clips each lake's raster to its polygon, computes spectral indices,
    texture features, band statistics, and water metrics.  Stores results
    in the ``lake_features`` table.

    Runs as a background task.  Poll ``GET /lake-features/status`` for
    real-time progress.
    """
    current = get_feature_progress()
    if current["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A lake feature generation pipeline is already running. "
            "Wait for it to complete before starting another.",
        )

    logger.info(
        "Lake feature generation request received",
        year=body.year,
        overwrite=body.overwrite,
    )

    try:
        background_tasks.add_task(
            generate_lake_features,
            year=body.year,
            overwrite=body.overwrite,
        )
    except Exception as exc:
        logger.error(
            "Failed to start lake feature pipeline",
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return GenerateLakeFeaturesResponse(
        status="queued",
        message=(
            "Lake feature generation started in the background. "
            "Poll /lake-features/status for real-time progress."
        ),
    )


@router.get("/status", response_model=LakeFeatureProgressResponse)
async def get_status() -> LakeFeatureProgressResponse:
    """Return the real-time progress of the lake feature pipeline."""
    progress = get_feature_progress()
    return LakeFeatureProgressResponse(**progress)


@router.post("/generate-b8", response_model=GenerateLakeFeaturesResponse)
async def generate_b8(
    body: GenerateLakeFeaturesRequest,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_pipeline_permission("fetch_b8")),
) -> GenerateLakeFeaturesResponse:
    """
    Start fetching Sentinel-2 B8 (NIR) and computing its zonal statistics.

    Separate from the main B2-B7 pipeline — B8 is not part of the Prithvi
    band set used for embeddings, so it's fetched independently per active
    lake and merged into the existing ``lake_features`` row for that
    lake/year (adds ``b8_mean``/``b8_std``/``b8_min``/``b8_max``/``b8_median``,
    tracked via its own ``b8_status`` column).

    Only processes active lakes that already have a completed
    ``lake_features`` row for the given year (or all years, if null). Runs
    as a background task — poll ``GET /lake-features/status-b8`` for progress.
    """
    current = get_b8_feature_progress()
    if current["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A B8 feature generation pipeline is already running. "
            "Wait for it to complete before starting another.",
        )

    logger.info("B8 feature generation request received", year=body.year, overwrite=body.overwrite)

    try:
        background_tasks.add_task(
            generate_b8_features,
            year=body.year,
            overwrite=body.overwrite,
        )
    except Exception as exc:
        logger.error("Failed to start B8 feature pipeline", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return GenerateLakeFeaturesResponse(
        status="queued",
        message=(
            "B8 feature generation started in the background. "
            "Poll /lake-features/status-b8 for real-time progress."
        ),
    )


@router.get("/status-b8", response_model=LakeFeatureProgressResponse)
async def get_status_b8() -> LakeFeatureProgressResponse:
    """Return the real-time progress of the B8 feature pipeline."""
    progress = get_b8_feature_progress()
    return LakeFeatureProgressResponse(**progress)
