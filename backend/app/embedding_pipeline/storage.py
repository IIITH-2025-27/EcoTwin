"""
PostgreSQL storage helpers for the embedding pipeline.

One ``regions`` row per lake-year holds the combined ``embedding`` used by
similarity and forecasting plus the ``lake_embedding`` / ``shore_embedding``
parts it was blended from. All functions use a synchronous SQLAlchemy engine
because the pipeline runs in background threads, outside the FastAPI async
session.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.embedding_pipeline.batch_inference import LakeEmbeddingResult, blend
from app.ML_pipeline.constants import EMBEDDING_VERSION, PRITHVI_EMBEDDING_DIM

logger = structlog.get_logger(__name__)

# Insert-or-update the regions row for one lake-year; centre comes from lakes.
_UPSERT_SQL = """
    INSERT INTO regions (
        region_id, lake_id, year, center_lat, center_lon,
        embedding, lake_embedding, shore_embedding,
        lake_weight, lake_token_weight, shore_token_weight, tokens_encoded,
        embedding_version, status, error_message, created_at, updated_at
    )
    SELECT
        gen_random_uuid(), lake.lake_id, :year,
        COALESCE(ST_Y(lake.centroid), ST_Y(ST_Centroid(lake.geom)), lake.pour_lat, 0),
        COALESCE(ST_X(lake.centroid), ST_X(ST_Centroid(lake.geom)), lake.pour_long, 0),
        CAST(:embedding AS vector), CAST(:lake_embedding AS vector),
        CAST(:shore_embedding AS vector),
        :lake_weight, :lake_token_weight, :shore_token_weight, :tokens_encoded,
        :embedding_version, :status, :error_message, NOW(), NOW()
    FROM lakes AS lake
    WHERE lake.lake_id = :lake_id
    ON CONFLICT ON CONSTRAINT uq_regions_lake_year DO UPDATE SET
        embedding          = EXCLUDED.embedding,
        lake_embedding     = EXCLUDED.lake_embedding,
        shore_embedding    = EXCLUDED.shore_embedding,
        lake_weight        = EXCLUDED.lake_weight,
        lake_token_weight  = EXCLUDED.lake_token_weight,
        shore_token_weight = EXCLUDED.shore_token_weight,
        tokens_encoded     = EXCLUDED.tokens_encoded,
        embedding_version  = EXCLUDED.embedding_version,
        status             = EXCLUDED.status,
        error_message      = EXCLUDED.error_message,
        center_lat         = EXCLUDED.center_lat,
        center_lon         = EXCLUDED.center_lon,
        updated_at         = NOW()
"""


def _sync_engine():
    """Create a synchronous engine for background thread usage."""
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def _vec_literal(vec: Optional[np.ndarray]) -> Optional[str]:
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32)
    if arr.shape != (PRITHVI_EMBEDDING_DIM,):
        raise ValueError(f"Expected ({PRITHVI_EMBEDDING_DIM},), got {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("Embedding contains NaN/Inf values")
    return "[" + ",".join(str(float(v)) for v in arr) + "]"


def _parse_vec(raw: Optional[str]) -> Optional[np.ndarray]:
    """pgvector text form "[0.1,0.2,...]" → float32 array."""
    if raw is None:
        return None
    return np.array([float(x) for x in raw.strip("[]").split(",")], dtype=np.float32)


class EmbeddingStorage:
    """Manage lake-year embedding persistence in ``regions``."""

    def __init__(self) -> None:
        self._engine = _sync_engine()
        self._Session = sessionmaker(bind=self._engine)

    # ── Resumption ────────────────────────────────────────────────────────

    def is_completed(self, lake_id: int, year: int) -> bool:
        """True if this lake-year already has current-method embeddings that
        are newer than its merged image.

        An image merged again after the embedding was computed (re-download,
        new composite) makes the stored embedding stale, so it is redone.
        """
        sql = text("""
            SELECT 1
            FROM regions AS r
            JOIN lake_images AS li
              ON li.lake_id = r.lake_id AND li.year = r.year
             AND li.status = 'merged'
            WHERE r.lake_id = :lake_id AND r.year = :year
              AND r.status = 'completed'
              AND r.embedding_version = :version
              AND r.lake_embedding IS NOT NULL
              AND r.updated_at >= li.updated_at
        """)
        with self._Session() as session:
            row = session.execute(sql, {
                "lake_id": lake_id, "year": year, "version": EMBEDDING_VERSION,
            }).fetchone()
        return row is not None

    # ── Writes ────────────────────────────────────────────────────────────

    def upsert_lake_embeddings(
        self, lake_id: int, year: int, result: LakeEmbeddingResult
    ) -> None:
        """Store the combined embedding and its lake / shore parts."""
        self._upsert(lake_id, year, {
            "embedding": _vec_literal(result.combined),
            "lake_embedding": _vec_literal(result.lake),
            "shore_embedding": _vec_literal(result.shore),
            "lake_weight": result.lake_weight,
            "lake_token_weight": result.lake_token_weight,
            "shore_token_weight": result.shore_token_weight,
            "tokens_encoded": result.tokens_encoded,
            "status": "completed",
            "error_message": None,
        })

    def mark_failed(self, lake_id: int, year: int, error_message: str) -> None:
        """Record a failed lake-year under the current method.

        Any older embedding on the row is cleared so a legacy vector is
        never compared against current-method ones.
        """
        self._upsert(lake_id, year, {
            "embedding": None,
            "lake_embedding": None,
            "shore_embedding": None,
            "lake_weight": None,
            "lake_token_weight": None,
            "shore_token_weight": None,
            "tokens_encoded": None,
            "status": "failed",
            "error_message": error_message[:2000],
        })

    def _upsert(self, lake_id: int, year: int, values: Dict) -> None:
        params = {
            "lake_id": lake_id,
            "year": year,
            "embedding_version": EMBEDDING_VERSION,
            **values,
        }
        with self._Session() as session:
            result = session.execute(text(_UPSERT_SQL), params)
            if result.rowcount != 1:
                raise ValueError(f"Lake {lake_id} was not found")
            session.commit()

    # ── Re-blend from stored parts ────────────────────────────────────────

    def reblend(
        self,
        lake_weight: float,
        years: Optional[List[int]] = None,
        lake_ids: Optional[List[int]] = None,
        on_row=None,
        on_total=None,
    ) -> Tuple[int, int]:
        """Recompute ``embedding`` from stored lake / shore parts.

        No Prithvi inference — only the weighted blend is redone. Returns
        ``(updated, skipped)``; ``on_total(n)`` is called once with the row
        count and ``on_row(lake_id, year)`` per row, for progress reporting.
        """
        if not 0.0 <= lake_weight <= 1.0:
            raise ValueError("lake_weight must be within [0, 1]")

        conditions = [
            "embedding_version = :version",
            "lake_embedding IS NOT NULL",
        ]
        params: Dict = {"version": EMBEDDING_VERSION}
        if years:
            conditions.append("year = ANY(:years)")
            params["years"] = years
        if lake_ids:
            conditions.append("lake_id = ANY(:lake_ids)")
            params["lake_ids"] = lake_ids

        select_sql = text(f"""
            SELECT lake_id, year, lake_embedding::text, shore_embedding::text
            FROM regions
            WHERE {' AND '.join(conditions)}
            ORDER BY lake_id, year
        """)
        update_sql = text("""
            UPDATE regions
            SET embedding   = CAST(:embedding AS vector),
                lake_weight = :lake_weight,
                updated_at  = NOW()
            WHERE lake_id = :lake_id AND year = :year
        """)

        updated = skipped = 0
        with self._Session() as session:
            rows = session.execute(select_sql, params).fetchall()
            if on_total is not None:
                on_total(len(rows))
            for lake_id, year, raw_lake, raw_shore in rows:
                try:
                    lake = _parse_vec(raw_lake)
                    shore = _parse_vec(raw_shore)
                    combined = blend(lake, shore, lake_weight)
                    session.execute(update_sql, {
                        "lake_id": lake_id,
                        "year": year,
                        "embedding": _vec_literal(combined),
                        "lake_weight": lake_weight if shore is not None else 1.0,
                    })
                    updated += 1
                except Exception as exc:
                    skipped += 1
                    logger.warning(
                        "Re-blend skipped row",
                        lake_id=lake_id, year=year, error=str(exc)[:200],
                    )
                if on_row is not None:
                    on_row(lake_id, year)
            session.commit()

        logger.info(
            "Embeddings re-blended",
            lake_weight=lake_weight, updated=updated, skipped=skipped,
        )
        return updated, skipped

    def weight_summary(self) -> Dict[int, Dict]:
        """Per year: lake-years with parts stored and the lake weights in use.

        Returns ``{year: {"lakes": n, "weights": {w: count}}}``. Lake-years
        without a shore part (always lake-only) are counted in ``lakes`` but
        not in ``weights``.
        """
        sql = text("""
            SELECT year,
                   CASE WHEN shore_embedding IS NULL THEN NULL
                        ELSE round(lake_weight::numeric, 3) END AS w,
                   count(*)
            FROM regions
            WHERE embedding_version = :version AND lake_embedding IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1, 2
        """)
        summary: Dict[int, Dict] = {}
        with self._Session() as session:
            for year, w, n in session.execute(sql, {"version": EMBEDDING_VERSION}):
                entry = summary.setdefault(int(year), {"lakes": 0, "weights": {}})
                entry["lakes"] += n
                if w is not None:
                    entry["weights"][float(w)] = n
        return summary

    def current_lake_weight(self) -> Optional[float]:
        """The lake weight most stored embeddings use (``None`` if none yet).

        New embeddings are blended with this weight so every lake-year stays
        comparable after a re-blend with a non-default weight.
        """
        totals: Dict[float, int] = {}
        for entry in self.weight_summary().values():
            for w, n in entry["weights"].items():
                totals[w] = totals.get(w, 0) + n
        return max(totals, key=totals.get) if totals else None

    def available_years(self) -> List[int]:
        """Years that have current-method lake / shore parts stored."""
        sql = text("""
            SELECT DISTINCT year FROM regions
            WHERE embedding_version = :version AND lake_embedding IS NOT NULL
            ORDER BY year
        """)
        with self._Session() as session:
            rows = session.execute(sql, {"version": EMBEDDING_VERSION}).fetchall()
        return [int(r[0]) for r in rows]

    def dispose(self) -> None:
        """Dispose of the engine connection pool."""
        self._engine.dispose()
