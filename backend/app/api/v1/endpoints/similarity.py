from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.dependencies import CacheDep, DatabaseDep
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.similarity import SimilaritySearchResponse
from app.services.similarity_service import SimilarityService

router = APIRouter(tags=["Similarity"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> SimilarityService:
    return SimilarityService(
        embedding_repo=EmbeddingRepository(db),
        region_repo=RegionRepository(db),
    )


@router.get("/{region_id}", response_model=SimilaritySearchResponse)
async def search_analog_ecosystems(
    region_id: UUID,
    year: Optional[int] = Query(None, description="Observation year (defaults to latest)"),
    top_k: int = Query(settings.DEFAULT_TOP_K, ge=1, le=50),
    cache: CacheDep = None,
    svc: SimilarityService = Depends(_service),
) -> SimilaritySearchResponse:
    """
    Retrieve the top-K most similar ecosystem regions using cosine similarity
    over Prithvi embeddings stored in pgvector.
    """
    cache_key = f"similarity:{region_id}:{year}:{top_k}"

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return SimilaritySearchResponse.model_validate_json(cached)

    result = await svc.search_analogs(region_id, year=year, top_k=top_k)

    if cache:
        await cache.set(cache_key, result.model_dump_json(), ttl=settings.REDIS_TTL)

    return result
