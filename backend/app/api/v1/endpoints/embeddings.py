"""
Embedding generation endpoints.

POST /embeddings/generate  — start the local Prithvi embedding pipeline
GET  /embeddings/status    — poll embedding generation progress
POST /embeddings/cancel    — cancel a running pipeline
GET  /embeddings/merge/options — years with lake / shore parts + lake weights in use
POST /embeddings/merge     — re-blend stored lake / shore parts with a new weight
GET  /embeddings/merge/status — poll re-blend progress
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.dependencies import DatabaseDep
from app.core.permissions import require_pipeline_permission
import asyncio

from app.core.config import settings
from app.embedding_pipeline.pipeline import (
    aggregate_lake_embeddings,
    cancel_embedding_pipeline,
    claim_embedding_run,
    claim_merge_run,
    fail_embedding_run,
    fail_merge_run,
    get_embedding_progress,
    get_merge_embedding_progress,
    run_embedding_pipeline,
)
from app.embedding_pipeline.storage import EmbeddingStorage
from app.ML_pipeline.constants import EMBEDDING_VERSION
from app.models.region import Region
from app.schemas.embedding_pipeline import (
    AvailableEmbeddingYearsResponse,
    EmbeddingProgressResponse,
    EmbeddingYearInfo,
    LakeWeightCount,
    GenerateEmbeddingsRequest,
    GenerateEmbeddingsResponse,
    MergeEmbeddingsRequest,
    MergeEmbeddingsResponse,
    MergeEmbeddingProgressResponse,
)

router = APIRouter(tags=["Embeddings"])
logger = structlog.get_logger(__name__)


async def get_available_embedding_years(
    db: DatabaseDep,
) -> list[int]:
    """Return years with current-method lake / shore embedding parts stored."""
    try:
        rows = await db.execute(
            select(Region.year)
            .where(
                Region.embedding_version == EMBEDDING_VERSION,
                Region.lake_embedding.is_not(None),
            )
            .distinct()
            .order_by(Region.year.asc())
        )
        years = [int(year) for (year,) in rows.all()]
    except SQLAlchemyError as exc:
        logger.exception(
            "Failed to query available embedding years",
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load available embedding years. Please try again.",
        ) from exc

    if not years:
        logger.warning(
            "No lake / shore embeddings available for re-blend",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No lake / shore embeddings are available to re-blend yet.",
        )

    logger.info(
        "Available embedding years loaded",
        years=years,
    )
    return years


@router.post("/generate", response_model=GenerateEmbeddingsResponse)
async def generate_embeddings(
    body: GenerateEmbeddingsRequest,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_pipeline_permission("generate_embeddings")),
) -> GenerateEmbeddingsResponse:
    """
    Start the local Prithvi embedding pipeline.

    Encodes each lake and its 500 m shore ring from the merged 30 m
    GeoTIFFs with Prithvi, pools lake / shore parts and blends them.
    No GEE queries.

    Runs as a background task. Poll ``GET /embeddings/status`` for progress.
    """
    if not claim_embedding_run():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An embedding generation or merge is already running. "
            "Cancel it first or wait for it to complete.",
        )

    total_estimate = (
        (len(body.lake_ids) if body.lake_ids else 0) * len(body.years)
    )

    logger.info(
        "Embedding generation request received",
        lake_ids=body.lake_ids,
        years=body.years,
    )

    try:
        background_tasks.add_task(
            run_embedding_pipeline,
            lake_ids=body.lake_ids,
            years=body.years,
            lake_weight=body.lake_weight,
        )
    except Exception as exc:
        logger.error("Failed to start embedding pipeline", error=str(exc))
        fail_embedding_run(f"Failed to start: {str(exc)[:300]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return GenerateEmbeddingsResponse(
        status="queued",
        total_tasks=total_estimate,
        message=(
            "Embedding generation started in the background. "
            "Poll /embeddings/status for real-time progress."
        ),
    )


def _weight_summary() -> dict:
    storage = EmbeddingStorage()
    try:
        return {
            "summary": storage.weight_summary(),
            "current": storage.current_lake_weight(),
        }
    finally:
        storage.dispose()


@router.get("/merge/options", response_model=AvailableEmbeddingYearsResponse)
async def get_merge_available_years() -> AvailableEmbeddingYearsResponse:
    """Years with lake / shore embeddings, and the lake weights in use.

    An empty list (not 404) when nothing has been generated yet.
    """
    info = await asyncio.to_thread(_weight_summary)
    summary = info["summary"]
    return AvailableEmbeddingYearsResponse(
        years=sorted(summary),
        year_details=[
            EmbeddingYearInfo(
                year=year,
                lakes=entry["lakes"],
                weights=[
                    LakeWeightCount(lake_weight=w, lakes=n)
                    for w, n in sorted(entry["weights"].items())
                ],
            )
            for year, entry in sorted(summary.items())
        ],
        current_lake_weight=info["current"],
        default_lake_weight=settings.EMBEDDING_LAKE_WEIGHT,
    )


@router.post("/merge", response_model=MergeEmbeddingsResponse)
async def merge_embeddings(
    body: MergeEmbeddingsRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    _perm: None = Depends(require_pipeline_permission("merge_embeddings")),
) -> MergeEmbeddingsResponse:
    """Re-blend ``regions.embedding`` from stored lake / shore parts.

    Recomputes ``normalize(w · lake + (1 − w) · shore)`` for the selected
    years with ``body.lake_weight`` (default ``EMBEDDING_LAKE_WEIGHT``).
    No Prithvi inference.
    """
    if body.country.lower() != "india":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only India is currently supported for embedding merge.",
        )

    available_years = await get_available_embedding_years(db)
    unavailable_years = sorted(set(body.years) - set(available_years))
    if unavailable_years:
        logger.warning(
            "Embedding merge requested with unavailable years",
            unavailable_years=unavailable_years,
            available_years=available_years,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The selected years have no lake / shore embeddings: "
                f"{unavailable_years}."
            ),
        )

    logger.info(
        "Embedding merge request received",
        country=body.country,
        years=body.years,
        lake_weight=body.lake_weight,
    )

    if not claim_merge_run():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An embedding merge or generation is already running. "
            "Wait for it to complete.",
        )

    try:
        background_tasks.add_task(
            aggregate_lake_embeddings,
            years=body.years,
            lake_weight=body.lake_weight,
        )
    except Exception as exc:
        logger.error("Failed to start embedding merge", error=str(exc))
        fail_merge_run(f"Failed to start: {str(exc)[:300]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return MergeEmbeddingsResponse(
        status="queued",
        total_tasks=len(body.years),
        message=(
            "Embedding merge started. "
            "Poll /embeddings/merge/status for real-time progress."
        ),
    )


@router.get("/merge/status", response_model=MergeEmbeddingProgressResponse)
async def get_merge_status() -> MergeEmbeddingProgressResponse:
    """Return the real-time progress of the lake embedding merge."""
    progress = get_merge_embedding_progress()
    return MergeEmbeddingProgressResponse(**progress)


@router.get("/status", response_model=EmbeddingProgressResponse)
async def get_status() -> EmbeddingProgressResponse:
    """Return the real-time progress of the embedding pipeline."""
    progress = get_embedding_progress()
    return EmbeddingProgressResponse(**progress)


@router.post("/cancel")
async def cancel_pipeline() -> dict:
    """Request cancellation of the running embedding pipeline."""
    cancelled = cancel_embedding_pipeline()
    return {"cancelled": cancelled}
