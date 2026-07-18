"""
Embedding generation endpoints.

POST /embeddings/generate  — start the local Prithvi embedding pipeline
GET  /embeddings/status    — poll embedding generation progress
POST /embeddings/cancel    — cancel a running pipeline
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.embedding_pipeline.pipeline import (
    cancel_embedding_pipeline,
    get_embedding_progress,
    run_embedding_pipeline,
)
from app.schemas.embedding_pipeline import (
    EmbeddingProgressResponse,
    GenerateEmbeddingsRequest,
    GenerateEmbeddingsResponse,
)

router = APIRouter(tags=["Embeddings"])
logger = structlog.get_logger(__name__)


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
