"""
POST /sync/start  — trigger the ML data-ingestion pipeline for selected Indian states.
GET  /sync/states — return the list of supported state names.
GET  /sync/status/{job_id} — poll aggregated Celery task status for a sync job.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, HTTPException, status

from app.ML_pipeline.constants import PIPELINE_YEAR_END, PIPELINE_YEAR_START
from app.schemas.sync import (
    INDIA_STATE_CENTROIDS,
    MAX_STATES_PER_SYNC,
    SyncJobResponse,
    SyncRequest,
)
from app.services.sync_service import get_job_status, start_sync

router = APIRouter(tags=["Sync"])
logger = structlog.get_logger(__name__)


@router.get("/states")
async def list_states() -> dict:
    """
    Return the list of all supported Indian state / UT names with their
    centroid coordinates.  Used by the frontend multi-select.
    """
    return {
        "states": [
            {"name": name, "lat": lat, "lon": lon}
            for name, (lat, lon) in sorted(INDIA_STATE_CENTROIDS.items())
        ],
        "max_selection": MAX_STATES_PER_SYNC,
        "year_start": PIPELINE_YEAR_START,
        "year_end": PIPELINE_YEAR_END,
    }


@router.post("/start", response_model=SyncJobResponse, status_code=202)
async def start_sync_job(body: SyncRequest) -> SyncJobResponse:
    """
    Wipe (or back up) existing data for the selected states then dispatch
    the three-phase ML pipeline (GEE ingest → Prithvi embedding → classification)
    for every requested state × year combination.

    The endpoint validates:
    - ``confirmed=true``  (user must have accepted the warning dialog)
    - max 3 states
    - recognised state names

    Returns immediately with ``status="queued"`` and the number of Celery
    tasks dispatched.  Monitor pipeline progress via Flower or the Celery
    result backend.
    """
    logger.info(
        "Sync request received",
        states=body.states,
        sync_mode=body.sync_mode,
        years=body.duration.resolved_years(),
    )

    try:
        # Run synchronous service logic off the async event loop
        result = await asyncio.to_thread(start_sync, body)
    except Exception as exc:
        logger.error("Sync endpoint error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    if result.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message,
        )

    return result


@router.get("/status/{job_id}")
async def get_sync_status(job_id: str) -> dict:
    """
    Poll the aggregated status of all Celery tasks belonging to a sync job.

    Returns counts + per-task status so the frontend can render a progress view.
    The job metadata expires from Redis after 24 h.
    """
    try:
        result = await asyncio.to_thread(get_job_status, job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    return result
