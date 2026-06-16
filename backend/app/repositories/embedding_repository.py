import time
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import RegionEmbedding
from app.repositories.base_repository import BaseRepository


class EmbeddingRepository(BaseRepository[RegionEmbedding]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RegionEmbedding, session)

    async def get_by_region_year(
        self, region_id: UUID, year: int
    ) -> Optional[RegionEmbedding]:
        result = await self.session.execute(
            select(RegionEmbedding).where(
                RegionEmbedding.region_id == region_id,
                RegionEmbedding.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(self, region_id: UUID) -> Optional[RegionEmbedding]:
        result = await self.session.execute(
            select(RegionEmbedding)
            .where(RegionEmbedding.region_id == region_id)
            .order_by(RegionEmbedding.year.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        exclude_region_id: Optional[UUID] = None,
        year: Optional[int] = None,
    ) -> Tuple[List[dict], float]:
        """
        Cosine similarity search via pgvector IVFFlat index.

        Returns (results, latency_ms).  Results are ordered most-similar first
        and each row contains: region_id, year, center_lat, center_lon,
        dominant_ecosystem, similarity_score.
        """
        start = time.perf_counter()

        # Build the embedding literal for pgvector
        vec_literal = "[" + ",".join(map(str, query_embedding)) + "]"

        conditions: List[str] = []
        if exclude_region_id:
            conditions.append(f"re.region_id != '{exclude_region_id}'")
        if year is not None:
            conditions.append(f"re.year = {year}")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = text(f"""
            SELECT
                re.region_id,
                re.year,
                r.center_lat,
                r.center_lon,
                rf.dominant_ecosystem,
                (1 - (re.embedding <=> '{vec_literal}'::vector))::float AS similarity_score
            FROM region_embeddings re
            JOIN regions r ON r.region_id = re.region_id
            LEFT JOIN region_features rf
                ON rf.region_id = re.region_id AND rf.year = re.year
            {where_clause}
            ORDER BY re.embedding <=> '{vec_literal}'::vector
            LIMIT :top_k
        """)

        result = await self.session.execute(sql, {"top_k": top_k})
        rows = [dict(row) for row in result.mappings().all()]
        latency_ms = (time.perf_counter() - start) * 1_000

        return rows, latency_ms
