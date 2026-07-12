from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.dependencies import CacheDep, DatabaseDep
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.similarity import SimilarityMethod, SimilaritySearchResponse
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
    method: SimilarityMethod = Query(
        SimilarityMethod.COSINE,
        description=(
            "Vector similarity method. "
            "cosine: 1−cosine_distance (IVFFlat index, recommended). "
            "euclidean: 1/(1+L2_distance). "
            "knn: inner-product (equivalent to cosine for unit-norm embeddings)."
        ),
    ),
    cache: CacheDep = None,
    svc: SimilarityService = Depends(_service),
) -> SimilaritySearchResponse:
    """
    Retrieve top-K analog ecosystem regions.
    Supports three vector search methods: cosine, euclidean, knn.
    """
    cache_key = f"similarity:{region_id}:{year}:{top_k}:{method.value}"

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return SimilaritySearchResponse.model_validate_json(cached)

    result = await svc.search_analogs(region_id, year=year, top_k=top_k, method=method)

    if cache:
        await cache.set(cache_key, result.model_dump_json())

    return result
