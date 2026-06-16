from typing import Optional
from uuid import UUID

import structlog

from app.core.config import settings
from app.core.exceptions import EmbeddingNotFoundException, RegionNotFoundException
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.similarity import AnalogResult, SimilarityMethod, SimilaritySearchResponse

logger = structlog.get_logger(__name__)


class SimilarityService:
    def __init__(
        self,
        embedding_repo: EmbeddingRepository,
        region_repo: RegionRepository,
    ) -> None:
        self._embedding_repo = embedding_repo
        self._region_repo = region_repo

    async def search_analogs(
        self,
        region_id: UUID,
        year: Optional[int] = None,
        top_k: int = 10,
        exclude_same_region: bool = True,
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> SimilaritySearchResponse:
        region = await self._region_repo.get_by_id(region_id)
        if not region:
            raise RegionNotFoundException(str(region_id))

        if year is not None:
            record = await self._embedding_repo.get_by_region_year(region_id, year)
        else:
            record = await self._embedding_repo.get_latest(region_id)

        if not record:
            raise EmbeddingNotFoundException(str(region_id))

        query_year = record.year
        exclude_id = region_id if exclude_same_region else None

        raw_results, latency_ms = await self._embedding_repo.search_similar(
            query_embedding=list(record.embedding),
            top_k=min(top_k, settings.MAX_TOP_K),
            exclude_region_id=exclude_id,
            year=year,
            method=method,
        )

        logger.info(
            "Similarity search completed",
            region_id=str(region_id),
            year=query_year,
            method=method.value,
            results=len(raw_results),
            latency_ms=round(latency_ms, 1),
        )

        analogs = [
            AnalogResult(
                region_id=row["region_id"],
                center_lat=row["center_lat"],
                center_lon=row["center_lon"],
                similarity_score=max(0.0, min(1.0, float(row["similarity_score"]))),
                year=row["year"],
                dominant_ecosystem=row.get("dominant_ecosystem"),
            )
            for row in raw_results
        ]

        return SimilaritySearchResponse(
            query_region_id=region_id,
            query_year=query_year,
            analogs=analogs,
            search_latency_ms=round(latency_ms, 2),
            method=method,
        )
