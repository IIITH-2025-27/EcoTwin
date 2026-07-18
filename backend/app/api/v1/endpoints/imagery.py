"""
Lake imagery download endpoints.

POST /imagery/fetch     — start downloading Sentinel-2 composites (background task)
GET  /imagery/status    — poll download progress
POST /imagery/cancel    — cancel a running download
GET  /imagery/lakes/{lake_id} — per-lake download status (with tile details)
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.core.dependencies import DatabaseDep
from app.image_acquisition.pipeline import (
    cancel_imagery_pipeline,
    get_imagery_progress,
    run_imagery_pipeline,
)
from app.models.lake_image import LakeImage
from app.models.lake_tile import LakeTile
from app.schemas.imagery import (
    FetchImagesRequest,
    FetchImagesResponse,
    ImageryProgressResponse,
    LakeImageRecord,
    LakeImageStatusResponse,
    LakeTileRecord,
)

router = APIRouter(tags=["Imagery"])
logger = structlog.get_logger(__name__)


@router.post("/fetch", response_model=FetchImagesResponse)
async def fetch_images(
    body: FetchImagesRequest,
    background_tasks: BackgroundTasks,
) -> FetchImagesResponse:
    """
    Start downloading Sentinel-2 GeoTIFF composites for the specified
    lakes and years.

    Runs as a background task. Poll ``GET /imagery/status`` for progress.
    """
    # Check if a pipeline is already running
    current = get_imagery_progress()
    if current["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An imagery download is already in progress. "
            "Cancel it first or wait for it to complete.",
        )

    total_estimate = (
        (len(body.lake_ids) if body.lake_ids else 0) * len(body.years)
    )

    logger.info(
        "Imagery fetch request received",
        lake_ids=body.lake_ids,
        years=body.years,
        total_estimate=total_estimate,
    )

    try:
        background_tasks.add_task(
            run_imagery_pipeline,
            lake_ids=body.lake_ids,
            years=body.years,
        )
    except Exception as exc:
        logger.error("Failed to start imagery pipeline", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return FetchImagesResponse(
        status="queued",
        total_tasks=total_estimate,
        message=(
            "Image download started in the background. "
            "Poll /imagery/status for real-time progress."
        ),
    )


@router.get("/status", response_model=ImageryProgressResponse)
async def get_status() -> ImageryProgressResponse:
    """Return the real-time progress of the imagery download pipeline."""
    progress = get_imagery_progress()
    return ImageryProgressResponse(**progress)


@router.post("/cancel")
async def cancel_download() -> dict:
    """Request cancellation of the running imagery download."""
    cancelled = cancel_imagery_pipeline()
    return {"cancelled": cancelled}


@router.get("/lakes/{lake_id}", response_model=LakeImageStatusResponse)
async def get_lake_image_status(
    lake_id: int,
    db: DatabaseDep,
) -> LakeImageStatusResponse:
    """Return the download status for all imagery associated with a lake,
    including per-tile details."""
    # Lake-level images
    rows = (
        await db.execute(
            select(LakeImage)
            .where(LakeImage.lake_id == lake_id)
            .order_by(LakeImage.year.desc())
        )
    ).scalars().all()

    images = [
        LakeImageRecord(
            year=row.year,
            file_path=row.file_path,
            status=row.status,
            file_size_bytes=row.file_size_bytes,
            error_message=row.error_message,
            retry_count=row.retry_count,
        )
        for row in rows
    ]

    # Tile-level details
    tile_rows = (
        await db.execute(
            select(LakeTile)
            .where(LakeTile.lake_id == lake_id)
            .order_by(LakeTile.year.desc(), LakeTile.tile_index)
        )
    ).scalars().all()

    tiles = [
        LakeTileRecord(
            tile_index=row.tile_index,
            status=row.status,
            image_path=row.image_path,
            bbox=row.bbox,
            file_size_bytes=row.file_size_bytes,
            error_message=row.error_message,
            retry_count=row.retry_count,
        )
        for row in tile_rows
    ]

    return LakeImageStatusResponse(
        lake_id=lake_id,
        images=images,
        tiles=tiles,
    )
