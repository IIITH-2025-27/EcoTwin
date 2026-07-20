"""
PostgreSQL storage helpers for the embedding pipeline.

All functions use a synchronous SQLAlchemy engine because the embedding
pipeline runs in background threads, outside the FastAPI async session.
"""

from __future__ import annotations

import math
from typing import List, Set

import numpy as np
import structlog
from shapely.geometry import box, mapping
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.ML_pipeline.constants import PRITHVI_EMBEDDING_DIM

logger = structlog.get_logger(__name__)


def _sync_engine():
    """Create a synchronous engine for background thread usage."""
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


class EmbeddingStorage:
    """Manage cell-level embedding persistence for the pipeline."""

    def __init__(self) -> None:
        self._engine = _sync_engine()
        self._Session = sessionmaker(bind=self._engine)

    # ── Status helpers ────────────────────────────────────────────────────

    def mark_cells_processing(
        self,
        lake_id: int,
        year: int,
        cell_numbers: List[int],
    ) -> None:
        """Set status = 'processing' for a batch of cells about to be inferred."""
        if not cell_numbers:
            return
        sql = text("""
            UPDATE sub_regions
            SET status     = 'processing',
                updated_at = NOW()
            WHERE lake_id     = :lake_id
              AND year        = :year
              AND cell_number = ANY(:cell_numbers)
              AND status     != 'completed'
        """)
        with self._Session() as session:
            session.execute(sql, {
                "lake_id": lake_id,
                "year": year,
                "cell_numbers": cell_numbers,
            })
            session.commit()

    def mark_cell_failed(
        self,
        lake_id: int,
        cell_number: int,
        year: int,
        error_message: str,
        coverage_percent: float | None = None,
        center_lat: float | None = None,
        center_lon: float | None = None,
        bounds_4326: tuple | None = None,
    ) -> None:
        """
        Set status = 'failed' and record the error for a single cell.

        When cell geometry/metadata is provided, upsert a failed sub-region row
        so failed cells are visible in the database on first attempt.
        """
        if (
            coverage_percent is not None
            and center_lat is not None
            and center_lon is not None
            and bounds_4326 is not None
        ):
            lon_min, lat_min, lon_max, lat_max = bounds_4326
            cell_wkt = box(lon_min, lat_min, lon_max, lat_max).wkt
            sql = text("""
                INSERT INTO sub_regions (
                    sub_region_id, lake_id, cell_number, year,
                    coverage_percent, center_lat, center_lon,
                    geom, embedding, status, error_message,
                    created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), :lake_id, :cell_number, :year,
                    :coverage_percent, :center_lat, :center_lon,
                    ST_GeomFromText(:geom_wkt, 4326),
                    NULL, 'failed', :error_message,
                    NOW(), NOW()
                )
                ON CONFLICT (lake_id, cell_number, year) DO UPDATE SET
                    coverage_percent = EXCLUDED.coverage_percent,
                    center_lat       = EXCLUDED.center_lat,
                    center_lon       = EXCLUDED.center_lon,
                    geom             = EXCLUDED.geom,
                    status           = 'failed',
                    error_message    = EXCLUDED.error_message,
                    updated_at       = NOW()
            """)
            params = {
                "lake_id": lake_id,
                "cell_number": cell_number,
                "year": year,
                "coverage_percent": coverage_percent,
                "center_lat": center_lat,
                "center_lon": center_lon,
                "geom_wkt": cell_wkt,
                "error_message": error_message[:2000],
            }
        else:
            sql = text("""
                UPDATE sub_regions
                SET status        = 'failed',
                    error_message = :error_message,
                    updated_at    = NOW()
                WHERE lake_id     = :lake_id
                  AND cell_number = :cell_number
                  AND year        = :year
            """)
            params = {
                "lake_id": lake_id,
                "cell_number": cell_number,
                "year": year,
                "error_message": error_message[:2000],
            }

        with self._Session() as session:
            session.execute(sql, params)
            session.commit()

    # ── Cell embedding persistence ────────────────────────────────────────

    def upsert_cell_embedding(
        self,
        lake_id: int,
        cell_number: int,
        year: int,
        embedding: np.ndarray,
        coverage_percent: float,
        center_lat: float,
        center_lon: float,
        bounds_4326: tuple,
    ) -> None:
        """
        Insert or update a sub_regions row with the cell embedding.

        Uses the existing ``sub_regions`` table which already has a
        ``Vector(768)`` embedding column.
        Sets ``status = 'completed'`` and clears any previous error.
        """
        # Validate embedding
        if embedding.shape != (PRITHVI_EMBEDDING_DIM,):
            raise ValueError(f"Expected ({PRITHVI_EMBEDDING_DIM},), got {embedding.shape}")
        if not np.isfinite(embedding).all():
            raise ValueError("Embedding contains NaN/Inf values")

        # Build WKT for the cell polygon
        lon_min, lat_min, lon_max, lat_max = bounds_4326
        cell_polygon = box(lon_min, lat_min, lon_max, lat_max)
        cell_wkt = cell_polygon.wkt

        # Build pgvector literal
        vec_literal = "[" + ",".join(str(float(v)) for v in embedding) + "]"

        sql = text("""
            INSERT INTO sub_regions (
                sub_region_id, lake_id, cell_number, year,
                coverage_percent, center_lat, center_lon,
                geom, embedding, status, error_message,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :lake_id, :cell_number, :year,
                :coverage_percent, :center_lat, :center_lon,
                ST_GeomFromText(:geom_wkt, 4326),
                CAST(:embedding AS vector),
                'completed', NULL,
                NOW(), NOW()
            )
            ON CONFLICT (lake_id, cell_number, year) DO UPDATE SET
                coverage_percent = EXCLUDED.coverage_percent,
                center_lat       = EXCLUDED.center_lat,
                center_lon       = EXCLUDED.center_lon,
                geom             = EXCLUDED.geom,
                embedding        = EXCLUDED.embedding,
                status           = 'completed',
                error_message    = NULL,
                updated_at       = NOW()
        """)

        with self._Session() as session:
            session.execute(sql, {
                "lake_id": lake_id,
                "cell_number": cell_number,
                "year": year,
                "coverage_percent": coverage_percent,
                "center_lat": center_lat,
                "center_lon": center_lon,
                "geom_wkt": cell_wkt,
                "embedding": vec_literal,
            })
            session.commit()

    # ── Resumption queries ────────────────────────────────────────────────

    def get_processed_cells(self, lake_id: int, year: int) -> Set[int]:
        """
        Return the set of cell_numbers that are already completed.

        Used for resumption — skip cells that were already successfully processed.
        Failed/pending/processing cells are NOT included, so they get retried.
        """
        sql = text("""
            SELECT cell_number
            FROM sub_regions
            WHERE lake_id = :lake_id
              AND year     = :year
              AND status   = 'completed'
        """)

        with self._Session() as session:
            rows = session.execute(sql, {
                "lake_id": lake_id,
                "year": year,
            }).fetchall()

        return {row[0] for row in rows}

    def dispose(self) -> None:
        """Dispose of the engine connection pool."""
        self._engine.dispose()
