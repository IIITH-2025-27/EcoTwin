import time
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import RegionEmbedding
from app.repositories.base_repository import BaseRepository
from app.schemas.similarity import SimilarityMethod


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
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> Tuple[List[dict], float]:
        """
        Vector similarity search via pgvector.

        Supports three methods:
          cosine    — operator <=>  (cosine distance, IVFFlat index)
                      score = 1 − cosine_distance  ∈ [0, 1]
          euclidean — operator <->  (L2 distance)
                      score = 1 / (1 + L2_distance) ∈ (0, 1]
          knn       — operator <#>  (negative inner product)
                      score = (inner_product + 1) / 2  ∈ [0, 1]
                      Equivalent to cosine for L2-normalised embeddings.

        Returns (results, latency_ms). Results are ordered best-match first.
        Each row: region_id, year, center_lat, center_lon,
                  dominant_ecosystem, similarity_score.
        """
        start = time.perf_counter()

        vec_literal = "[" + ",".join(map(str, query_embedding)) + "]"

        conditions: List[str] = []
        if exclude_region_id:
            conditions.append(f"re.region_id != '{exclude_region_id}'")
        if year is not None:
            conditions.append(f"re.year = {year}")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        if method == SimilarityMethod.COSINE:
            # Cosine distance operator <=>
            # score = 1 - cosine_distance  (1.0 = identical, 0.0 = orthogonal)
            score_expr  = f"(1 - (re.embedding <=> '{vec_literal}'::vector))::float"
            order_expr  = f"re.embedding <=> '{vec_literal}'::vector"

        elif method == SimilarityMethod.EUCLIDEAN:
            # L2 (Euclidean) distance operator <->
            # score = 1 / (1 + distance)  — maps [0, ∞) → (0, 1]
            score_expr  = f"(1.0 / (1.0 + (re.embedding <-> '{vec_literal}'::vector)))::float"
            order_expr  = f"re.embedding <-> '{vec_literal}'::vector"

        else:  # KNN — inner product
            # Negative inner product operator <#>
            # For unit-norm vectors: inner_product ∈ [-1, 1], same as cosine similarity
            # score = (inner_product + 1) / 2  → [0, 1]
            score_expr  = f"((re.embedding <#> '{vec_literal}'::vector) * -1 + 1) / 2::float"
            order_expr  = f"re.embedding <#> '{vec_literal}'::vector"   # pgvector: <#> is negated, ASC = best

        sql = text(f"""
            SELECT
                re.region_id,
                re.year,
                r.center_lat,
                r.center_lon,
                rf.dominant_ecosystem,
                {score_expr} AS similarity_score
            FROM region_embeddings re
            JOIN regions r ON r.region_id = re.region_id
            LEFT JOIN region_features rf
                ON rf.region_id = re.region_id AND rf.year = re.year
            {where_clause}
            ORDER BY {order_expr}
            LIMIT :top_k
        """)

        result = await self.session.execute(sql, {"top_k": top_k})
        rows = [dict(row) for row in result.mappings().all()]
        latency_ms = (time.perf_counter() - start) * 1_000

        return rows, latency_ms
