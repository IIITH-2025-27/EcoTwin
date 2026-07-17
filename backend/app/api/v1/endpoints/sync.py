"""
POST /sync/start   — trigger the lake-region import and ML pipeline (background).
GET  /sync/country — return the default region source country and time bounds.
GET  /sync/status  — real-time progress of the running (or last completed) sync.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.schemas.sync import (
    HydroLakeBoundaryResponse,
    IndiaStateImportResponse,
    LakeImportResponse,
    SyncJobResponse,
    SyncRequest,
)
from app.services.sync_service import (
    cancel_sync,
    get_sync_progress,
    import_india_states,
    import_lakes_table,
    list_hydrolake_boundaries,
    start_sync,
)

router = APIRouter(tags=["Sync"])
logger = structlog.get_logger(__name__)


@router.get("/country")
async def get_sync_country() -> dict:
    """Return the default region source country used by the sync UI."""
    from app.core.config import settings  # noqa: PLC0415
    return {
        "country": "India",
        "year_start": 2016,
        "year_end": 2025,
        "max_year_range": settings.SYNC_MAX_YEAR_RANGE,
    }


@router.get("/hydrolakes/boundaries", response_model=list[HydroLakeBoundaryResponse])
async def get_hydrolake_boundaries(
    country: str = "India",
) -> list[HydroLakeBoundaryResponse]:
    """Return HydroLAKES boundary data for the requested country."""
    try:
        return await asyncio.to_thread(list_hydrolake_boundaries, country)
    except FileNotFoundError as exc:
        logger.warning("HydroLAKES boundary source unavailable", error=str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/lakes/import", response_model=LakeImportResponse)
async def import_lakes(
    country: str = "India",
) -> LakeImportResponse:
    """Import HydroLAKES shapefile rows into the lakes table."""
    try:
        return await asyncio.to_thread(import_lakes_table, country)
    except FileNotFoundError as exc:
        logger.warning("HydroLAKES shapefile unavailable", error=str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("HydroLAKES import failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lake import failed: {exc}",
        ) from exc


@router.post("/india-states/import", response_model=IndiaStateImportResponse)
async def import_india_state_boundaries() -> IndiaStateImportResponse:
    """Load India state/UT boundaries and backfill existing lake metadata."""
    try:
        return await asyncio.to_thread(import_india_states)
    except FileNotFoundError as exc:
        logger.warning("India states boundary source unavailable", error=str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("India states import failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"India states import failed: {exc}",
        ) from exc


@router.post("/start", response_model=SyncJobResponse)
async def start_sync_job(
    body: SyncRequest,
    background_tasks: BackgroundTasks,
) -> SyncJobResponse:
    """
    Start the lake-region import and ML pipeline in the background.

    Returns immediately. Poll ``GET /sync/status`` for real-time progress.
    """
    logger.info(
        "Sync request received",
        country=body.country,
        sync_mode=body.sync_mode,
        years=body.duration.resolved_years(),
    )

    try:
        background_tasks.add_task(start_sync, body, "global")
    except Exception as exc:
        logger.error("Sync endpoint error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return SyncJobResponse(
        job_id="global",
        status="queued",
        source_type=body.source_type,
        country=body.country,
        region_ids=[],
        years=body.duration.resolved_years(),
        sync_mode=body.sync_mode,
        tasks_dispatched=0,
        total_regions=0,
        inserted_regions=0,
        updated_regions=0,
        skipped_regions=0,
        message="Sync started in the background. Poll /sync/status for progress.",
    )


@router.post("/cancel")
async def cancel_sync_job(job_id: str | None = None) -> dict:
    """Request cancellation for the active sync job, or all active jobs when no job ID is provided."""
    try:
        return cancel_sync(job_id)
    except Exception as exc:
        logger.error("Sync cancel failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get("/status")
async def get_sync_status() -> dict:
    """
    Return the real-time progress of the currently running (or last completed) sync.

    Shape:
      status        — idle | running | done | failed
      total_lakes   — total lake×year pairs to process
      processed     — how many have finished (success or failed)
      success       — successfully processed count
      failed        — failed count
      current_lake  — lake ID currently being processed (null when idle/done)
      current_year  — year currently being processed (null when idle/done)
      errors        — list of error strings for failed items
    """
    return get_sync_progress()
