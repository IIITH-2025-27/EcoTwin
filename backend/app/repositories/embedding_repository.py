import json
import time
from types import SimpleNamespace
from typing import List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.similarity import SimilarityMethod

logger = structlog.get_logger(__name__)


class EmbeddingRepository:
    @staticmethod
    def _parse_embedding(raw) -> Optional[List[float]]:
        """Convert pgvector's raw output (string, list, or numpy array) to list[float]."""
        if raw is None:
            return None
        if isinstance(raw, (list, tuple)):
            return [float(x) for x in raw]
        if isinstance(raw, str):
            # pgvector returns strings like '[0.1,0.2,...]' through raw SQL
            try:
                return [float(x) for x in json.loads(raw)]
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse embedding string", raw_prefix=raw[:80])
                return None
        # numpy array or similar iterable
        try:
            return [float(x) for x in raw]
        except (TypeError, ValueError):
            logger.warning("Failed to parse embedding", type=type(raw).__name__)
            return None

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_region_year(
        self, region_id: UUID, year: int
    ) -> Optional[SimpleNamespace]:
        result = await self.session.execute(
            text(
                """
                SELECT region_id, lake_id, year, center_lat, center_lon, embedding
                FROM regions
                WHERE region_id = :region_id
                  AND year = :year
                  AND embedding IS NOT NULL
                """
            ),
            {"region_id": str(region_id), "year": year},
        )
        row = result.mappings().one_or_none()
        return SimpleNamespace(**row) if row else None

    async def get_latest(self, region_id: UUID) -> Optional[SimpleNamespace]:
        result = await self.session.execute(
            text(
                """
                SELECT region_id, lake_id, year, center_lat, center_lon, embedding
                FROM regions
                WHERE region_id = :region_id
                  AND embedding IS NOT NULL
                """
            ),
            {"region_id": str(region_id)},
        )
        row = result.mappings().one_or_none()
        return SimpleNamespace(**row) if row else None

    async def get_historical_embeddings_for_region(self, region_id: UUID) -> List[SimpleNamespace]:
        lake_row = await self.session.execute(
            text(
                """
                SELECT lake_id
                FROM regions
                WHERE region_id = :region_id
                LIMIT 1
                """
            ),
            {"region_id": str(region_id)},
        )
        lake_id = lake_row.scalar_one_or_none()
        if lake_id is None:
            return []

        result = await self.session.execute(
            text(
                """
                SELECT region_id, lake_id, year, center_lat, center_lon, embedding
                FROM regions
                WHERE lake_id = :lake_id
                  AND embedding IS NOT NULL
                ORDER BY year ASC
                """
            ),
            {"lake_id": lake_id},
        )
        records = []
        for row in result.mappings().all():
            parsed = self._parse_embedding(row["embedding"])
            if parsed is not None:
                records.append(SimpleNamespace(
                    region_id=row["region_id"],
                    lake_id=row["lake_id"],
                    year=row["year"],
                    center_lat=row["center_lat"],
                    center_lon=row["center_lon"],
                    embedding=parsed,
                ))
        logger.debug(
            "Fetched historical embeddings for lake",
            lake_id=lake_id,
            record_count=len(records),
        )
        return records

    async def get_all_historical_embeddings(self) -> List[dict]:
        result = await self.session.execute(
            text(
                """
                SELECT
                    r.region_id,
                    r.lake_id,
                    r.year,
                    r.center_lat,
                    r.center_lon,
                    r.embedding,
                    l.display_name
                FROM regions AS r
                LEFT JOIN lakes AS l ON l.lake_id = r.lake_id
                WHERE r.embedding IS NOT NULL
                ORDER BY r.lake_id ASC, r.year ASC
                """
            )
        )

        grouped: dict[int, dict] = {}
        for row in result.mappings().all():
            payload = grouped.setdefault(
                row["lake_id"],
                {
                    "lake_id": row["lake_id"],
                    "region_id": row["region_id"],
                    "latest_year": row["year"],
                    "center_lat": float(row["center_lat"]),
                    "center_lon": float(row["center_lon"]),
                    "dominant_ecosystem": row["display_name"],
                    "records": [],
                },
            )
            if row["year"] >= payload["latest_year"]:
                payload["region_id"] = row["region_id"]
                payload["latest_year"] = row["year"]
                payload["center_lat"] = float(row["center_lat"])
                payload["center_lon"] = float(row["center_lon"])
                payload["dominant_ecosystem"] = row["display_name"]
            parsed_emb = self._parse_embedding(row["embedding"])
            if parsed_emb is not None:
                payload["records"].append(
                    SimpleNamespace(
                        region_id=row["region_id"],
                        lake_id=row["lake_id"],
                        year=row["year"],
                        embedding=parsed_emb,
                    )
                )

        return list(grouped.values())


    async def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        exclude_region_id: Optional[UUID] = None,
        year: Optional[int] = None,
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> Tuple[List[dict], float]:
        start = time.perf_counter()

        vec_literal = "[" + ",".join(map(str, query_embedding)) + "]"

        conditions: List[str] = ["r.embedding IS NOT NULL"]
        if exclude_region_id:
            conditions.append("r.region_id != :exclude_region_id")
        if year is not None:
            conditions.append("r.year = :year")

        where_clause = "WHERE " + " AND ".join(conditions)

        if method == SimilarityMethod.COSINE:
            score_expr = f"(1 - (r.embedding <=> '{vec_literal}'::vector))::float"
            order_expr = f"r.embedding <=> '{vec_literal}'::vector"
        elif method == SimilarityMethod.EUCLIDEAN:
            score_expr = f"(1.0 / (1.0 + (r.embedding <-> '{vec_literal}'::vector)))::float"
            order_expr = f"r.embedding <-> '{vec_literal}'::vector"
        else:
            score_expr = f"((r.embedding <#> '{vec_literal}'::vector) * -1 + 1) / 2::float"
            order_expr = f"r.embedding <#> '{vec_literal}'::vector"

        sql = text(f"""
            SELECT
                r.region_id,
                r.year,
                r.center_lat,
                r.center_lon,
                rf.dominant_ecosystem,
                {score_expr} AS similarity_score
            FROM regions r
            LEFT JOIN region_features rf
                ON rf.region_id = r.region_id AND rf.year = r.year
            {where_clause}
            ORDER BY {order_expr}
            LIMIT :top_k
        """)

        params = {"top_k": top_k}
        if exclude_region_id:
            params["exclude_region_id"] = str(exclude_region_id)
        if year is not None:
            params["year"] = year

        result = await self.session.execute(sql, params)
        rows = [dict(row) for row in result.mappings().all()]
        latency_ms = (time.perf_counter() - start) * 1_000

        return rows, latency_ms