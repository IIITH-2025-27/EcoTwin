"""
Embedding generation endpoints.

POST /embeddings/generate  — start the local Prithvi embedding pipeline
GET  /embeddings/status    — poll embedding generation progress
POST /embeddings/cancel    — cancel a running pipeline
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.dependencies import DatabaseDep
from app.embedding_pipeline.pipeline import (
    aggregate_lake_embeddings,
    cancel_embedding_pipeline,
    get_embedding_progress,
    run_embedding_pipeline,
)
from app.models.sub_region import SubRegion
from app.schemas.embedding_pipeline import (
    AvailableEmbeddingYearsResponse,
    EmbeddingProgressResponse,
    GenerateEmbeddingsRequest,
    GenerateEmbeddingsResponse,
    MergeEmbeddingsRequest,
    MergeEmbeddingsResponse,
)

router = APIRouter(tags=["Embeddings"])
logger = structlog.get_logger(__name__)


async def get_available_embedding_years(
    db: DatabaseDep,
) -> list[int]:
    """Return all database-backed years with completed subregion embeddings."""
    try:
        rows = await db.execute(
            select(SubRegion.year)
            .where(
                SubRegion.status == "completed",
                SubRegion.embedding.is_not(None),
            )
            .distinct()
            .order_by(SubRegion.year.asc())
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
            "No completed subregion embeddings available for merge",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed subregion embeddings are available for merge.",
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
) -> GenerateEmbeddingsResponse:
    """
    Start the local Prithvi embedding pipeline.

    Processes downloaded GeoTIFFs through grid generation, cell extraction,
    GPU-batched inference, and weighted pooling. No GEE queries.

    Runs as a background task. Poll ``GET /embeddings/status`` for progress.
    """
    current = get_embedding_progress()
    if current["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An embedding pipeline is already running. "
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
        )
    except Exception as exc:
        logger.error("Failed to start embedding pipeline", error=str(exc))
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


@router.get("/merge/options", response_model=AvailableEmbeddingYearsResponse)
async def get_merge_available_years(
    db: DatabaseDep,
) -> AvailableEmbeddingYearsResponse:
    """Return all years with completed subregion embeddings available for merge."""
    years = await get_available_embedding_years(db)
    return AvailableEmbeddingYearsResponse(years=years)


@router.post("/merge", response_model=MergeEmbeddingsResponse)
async def merge_embeddings(
    body: MergeEmbeddingsRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
) -> MergeEmbeddingsResponse:
    """Aggregate per-tile embeddings into lake-level embeddings in the regions table."""
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
                "The selected years do not have completed subregion embeddings: "
                f"{unavailable_years}."
            ),
        )

    logger.info(
        "Embedding merge request received",
        country=body.country,
        years=body.years,
    )

    try:
        background_tasks.add_task(
            aggregate_lake_embeddings,
            years=body.years,
        )
    except Exception as exc:
        logger.error("Failed to start embedding merge", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return MergeEmbeddingsResponse(
        status="queued",
        total_tasks=len(body.years),
        message=(
            "Embedding merge started in the background. "
            "The aggregated embeddings will be written to the regions table."
        ),
    )


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
