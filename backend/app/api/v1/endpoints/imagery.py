"""
Lake imagery download and merge endpoints.

GET  /imagery/storage       — download location per year, free space, size estimate
POST /imagery/storage/check — validate a candidate download location
POST /imagery/fetch         — start downloading Sentinel-2 composites (background task)
GET  /imagery/status        — poll download progress
POST /imagery/cancel        — cancel a running download
GET  /imagery/lakes/{lake_id} — per-lake download status (with tile details)
GET  /imagery/merge/options  — available years for merging
POST /imagery/merge          — start merging tiles (background task)
GET  /imagery/merge/status   — poll merge progress
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, text

from app.core.config import settings
from app.core.dependencies import DatabaseDep
from app.core.permissions import require_pipeline_permission
from app.image_acquisition.pipeline import (
    cancel_imagery_pipeline,
    claim_imagery_run,
    fail_imagery_run,
    get_imagery_progress,
    run_imagery_pipeline,
)
from app.image_acquisition.merge_pipeline import (
    get_merge_progress,
    get_mergeable_years,
    run_merge_pipeline,
)
from app.image_acquisition.storage import (
    check_data_root,
    default_data_root,
    disk_usage,
    suggest_locations,
    summarise_year_roots,
)
from app.ML_pipeline.constants import PIPELINE_YEAR_END, PIPELINE_YEAR_START
from app.models.lake_image import LakeImage
from app.models.lake_tile import LakeTile
from app.schemas.imagery import (
    FetchImagesRequest,
    FetchImagesResponse,
    ImageryProgressResponse,
    LakeImageRecord,
    LakeImageStatusResponse,
    LakeTileRecord,
    MergeOptionsResponse,
    MergeProgressResponse,
    MergeTilesRequest,
    MergeTilesResponse,
    MergeYearOption,
    StorageCheckRequest,
    StorageCheckResponse,
    StorageInfoResponse,
    StorageLocation,
    YearRootUsage,
    YearStorage,
)

router = APIRouter(tags=["Imagery"])
logger = structlog.get_logger(__name__)

# Upper bound of the merged GeoTIFF size per active lake: the buffered
# bounding box at 30 m, 12 uint16 bands. Matches the real merged files to
# within the bbox overhead (the tiles are trimmed to the buffered shape).
_SIZE_ESTIMATE_SQL = text(
    """
    SELECT count(*) AS lakes,
           coalesce(sum(
               ((ST_XMax(g) - ST_XMin(g)) * 111320 * cos(radians((ST_YMin(g) + ST_YMax(g)) / 2)) + 2 * :buffer_m)
             * ((ST_YMax(g) - ST_YMin(g)) * 110574 + 2 * :buffer_m)
           ), 0) AS area_m2
    FROM (SELECT ST_Envelope(geom) AS g FROM lakes WHERE is_active) AS s
    """
)
_BYTES_PER_PIXEL = 12 * 2  # S2_BANDS_DOWNLOAD as uint16


@router.get("/storage", response_model=StorageInfoResponse)
async def get_storage(
    db: DatabaseDep,
    _perm: None = Depends(require_pipeline_permission("fetch_images")),
) -> StorageInfoResponse:
    """Storage location per year, free space, and a size estimate."""
    default_root = default_data_root()

    row = (
        await db.execute(
            _SIZE_ESTIMATE_SQL, {"buffer_m": settings.LAKE_IMAGERY_BUFFER_METRES}
        )
    ).one()
    scale_m = 30
    estimate = int(float(row.area_m2) / (scale_m * scale_m) * _BYTES_PER_PIXEL)

    # Where each year's files are, from the paths recorded in lake_images
    image_rows = (
        await db.execute(
            select(LakeImage.year, LakeImage.file_path, LakeImage.updated_at)
        )
    ).all()
    roots_by_year = await asyncio.to_thread(summarise_year_roots, image_rows)

    usage_cache: dict = {}

    async def usage_of(path):
        if path not in usage_cache:
            usage_cache[path] = await asyncio.to_thread(disk_usage, path) or {}
        return usage_cache[path]

    years = []
    for year in range(PIPELINE_YEAR_END, PIPELINE_YEAR_START - 1, -1):
        in_use = roots_by_year.get(year, [])
        current = default_root
        usage = await usage_of(current)
        roots = []
        for entry in in_use:
            u = await usage_of(entry["root"])
            roots.append(
                YearRootUsage(
                    root=str(entry["root"]),
                    lakes=entry["lakes"],
                    free_bytes=u.get("free_bytes"),
                    total_bytes=u.get("total_bytes"),
                )
            )
        years.append(
            YearStorage(
                year=year,
                data_root=str(current),
                is_default=not in_use,
                free_bytes=usage.get("free_bytes"),
                total_bytes=usage.get("total_bytes"),
                roots=roots,
            )
        )

    return StorageInfoResponse(
        default_root=str(default_root),
        years=years,
        active_lakes=row.lakes,
        estimated_bytes_per_year=estimate,
        suggestions=[StorageLocation(**s) for s in await asyncio.to_thread(suggest_locations)],
    )


@router.post("/storage/check", response_model=StorageCheckResponse)
async def check_storage(
    body: StorageCheckRequest,
    _perm: None = Depends(require_pipeline_permission("fetch_images")),
) -> StorageCheckResponse:
    """Validate a candidate download location without creating it."""
    try:
        path = check_data_root(body.path)
    except ValueError as exc:
        return StorageCheckResponse(path=body.path, valid=False, error=str(exc))
    usage = disk_usage(path) or {}
    return StorageCheckResponse(
        path=str(path),
        valid=True,
        free_bytes=usage.get("free_bytes"),
        total_bytes=usage.get("total_bytes"),
    )


@router.post("/fetch", response_model=FetchImagesResponse)
async def fetch_images(
    body: FetchImagesRequest,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_pipeline_permission("fetch_images")),
) -> FetchImagesResponse:
    """
    Start downloading Sentinel-2 GeoTIFF composites for the specified
    lakes and years.

    Runs as a background task. Poll ``GET /imagery/status`` for progress.
    """
    # Check if a pipeline is already running
    current = get_imagery_progress()
    if current["status"] in ("running", "cancelling"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An imagery download is already in progress. "
            "Cancel it first or wait for it to complete.",
        )

    # Storage root per year for this run: per-year path > data_root >
    # SENTINEL_DATA_DIR. Nothing is saved apart from the paths the download
    # writes to lake_tiles / lake_images.
    requested = {}
    for year in body.years:
        raw = (body.year_roots or {}).get(year) or body.data_root
        if raw is None:
            continue
        try:
            requested[year] = str(check_data_root(raw))
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail=f"{year}: {exc}"
            ) from exc

    if not claim_imagery_run({str(y): p for y, p in requested.items()}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An imagery download is already in progress.",
        )

    total_estimate = (
        (len(body.lake_ids) if body.lake_ids else 0) * len(body.years)
    )

    logger.info(
        "Imagery fetch request received",
        lake_ids=body.lake_ids,
        years=body.years,
        total_estimate=total_estimate,
        year_roots=requested,
    )

    try:
        background_tasks.add_task(
            run_imagery_pipeline,
            lake_ids=body.lake_ids,
            years=body.years,
            year_roots=requested,
        )
    except Exception as exc:
        logger.error("Failed to start imagery pipeline", error=str(exc))
        fail_imagery_run(f"Failed to start: {str(exc)[:300]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return FetchImagesResponse(
        status="queued",
        total_tasks=total_estimate,
        message=(
            "Image download started in the background"
            + (
                f" ({', '.join(f'{y} → {p}' for y, p in requested.items())})"
                if requested
                else f" into {default_data_root()}/<year>"
            )
            + ". "
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


# ── Merge endpoints ──────────────────────────────────────────────────────


@router.get("/merge/options", response_model=MergeOptionsResponse)
async def merge_options() -> MergeOptionsResponse:
    """Return years that have completed tiles available for merging."""
    years_data, data_root = get_mergeable_years()
    return MergeOptionsResponse(
        years=[
            MergeYearOption(
                year=y["year"],
                lake_count=y["lake_count"],
                output_path_pattern=y["output_path_pattern"],
            )
            for y in years_data
        ],
        data_root=data_root,
    )


@router.post("/merge", response_model=MergeTilesResponse)
async def merge_tiles(
    body: MergeTilesRequest,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_pipeline_permission("merge_image_tiles")),
) -> MergeTilesResponse:
    """
    Start merging downloaded tiles for all active lakes.

    Runs as a background task.  Poll ``GET /imagery/merge/status`` for progress.
    """
    current = get_merge_progress()
    if current["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A merge is already in progress. Wait for it to complete.",
        )

    logger.info(
        "Merge request received",
        years=body.years,
        delete_tiles=body.delete_tiles,
    )

    try:
        background_tasks.add_task(
            run_merge_pipeline,
            years=body.years,
            delete_tiles=body.delete_tiles,
        )
    except Exception as exc:
        logger.error("Failed to start merge pipeline", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return MergeTilesResponse(
        status="queued",
        message=(
            "Tile merge started in the background. "
            "Poll /imagery/merge/status for real-time progress."
        ),
    )


@router.get("/merge/status", response_model=MergeProgressResponse)
async def merge_status() -> MergeProgressResponse:
    """Return the real-time progress of the merge pipeline."""
    progress = get_merge_progress()
    return MergeProgressResponse(**progress)
