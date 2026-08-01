"""
Lake feature extraction endpoints.

POST /lake-features/generate  — start computing ecological features (background task)
GET  /lake-features/status    — poll feature generation progress
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.core.dependencies import DatabaseDep
from app.services.lake_feature_generator import (
    generate_lake_features,
    get_feature_progress,
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
