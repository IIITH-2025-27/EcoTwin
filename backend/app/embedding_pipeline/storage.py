"""
PostgreSQL storage helpers for the embedding pipeline.

All functions use a synchronous SQLAlchemy engine because the embedding
pipeline runs in background threads, outside the FastAPI async session.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Optional, Set

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
    """Manage cell-level and lake-level embedding persistence."""

    def __init__(self) -> None:
        self._engine = _sync_engine()
        self._Session = sessionmaker(bind=self._engine)

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
                geom, embedding, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :lake_id, :cell_number, :year,
                :coverage_percent, :center_lat, :center_lon,
                ST_GeomFromText(:geom_wkt, 4326),
                :embedding::vector,
                NOW(), NOW()
            )
            ON CONFLICT (lake_id, cell_number, year) DO UPDATE SET
                coverage_percent = EXCLUDED.coverage_percent,
                center_lat       = EXCLUDED.center_lat,
                center_lon       = EXCLUDED.center_lon,
                geom             = EXCLUDED.geom,
                embedding        = EXCLUDED.embedding,
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

    def upsert_lake_embedding(
        self,
        lake_id: int,
        year: int,
        embedding: np.ndarray,
        num_cells: int,
    ) -> None:
        """Insert or update the aggregated lake-level embedding."""
        if embedding.shape != (PRITHVI_EMBEDDING_DIM,):
            raise ValueError(f"Expected ({PRITHVI_EMBEDDING_DIM},), got {embedding.shape}")
        if not np.isfinite(embedding).all():
            raise ValueError("Lake embedding contains NaN/Inf values")

        vec_literal = "[" + ",".join(str(float(v)) for v in embedding) + "]"
        now = datetime.now(timezone.utc)

        sql = text("""
            INSERT INTO lake_embeddings (
                lake_id, year, embedding, num_cells, status, created_at, updated_at
            ) VALUES (
                :lake_id, :year, :embedding::vector, :num_cells,
                'completed', :now, :now
            )
            ON CONFLICT ON CONSTRAINT uq_lake_embedding_lake_year DO UPDATE SET
                embedding  = EXCLUDED.embedding,
                num_cells  = EXCLUDED.num_cells,
                status     = 'completed',
                updated_at = EXCLUDED.updated_at
        """)

        with self._Session() as session:
            session.execute(sql, {
                "lake_id": lake_id,
                "year": year,
                "embedding": vec_literal,
                "num_cells": num_cells,
                "now": now,
            })
            session.commit()

        logger.info(
            "Lake embedding stored",
            lake_id=lake_id,
            year=year,
            num_cells=num_cells,
        )

    def get_processed_cells(self, lake_id: int, year: int) -> Set[int]:
        """
        Return the set of cell_numbers that already have embeddings.

        Used for resumption — skip cells that were already processed.
        """
        sql = text("""
            SELECT cell_number
            FROM sub_regions
            WHERE lake_id = :lake_id
              AND year     = :year
              AND embedding IS NOT NULL
        """)

        with self._Session() as session:
            rows = session.execute(sql, {
                "lake_id": lake_id,
                "year": year,
            }).fetchall()

        return {row[0] for row in rows}

    def get_all_cell_embeddings(
        self, lake_id: int, year: int
    ) -> List[tuple]:
        """
        Load all cell embeddings for a lake/year for pooling.

        Returns list of (cell_number, embedding_vector, coverage_percent).
        """
        sql = text("""
            SELECT cell_number, embedding::text, coverage_percent
            FROM sub_regions
            WHERE lake_id = :lake_id
              AND year     = :year
              AND embedding IS NOT NULL
            ORDER BY cell_number
        """)

        with self._Session() as session:
            rows = session.execute(sql, {
                "lake_id": lake_id,
                "year": year,
            }).fetchall()

        results = []
        for row in rows:
            cell_num = row[0]
            # Parse pgvector text representation "[0.1,0.2,...]"
            raw = str(row[1]).strip("[]")
            vec = np.array([float(v) for v in raw.split(",")], dtype=np.float32)
            coverage = float(row[2])
            results.append((cell_num, vec, coverage))

        return results

    def is_lake_embedding_complete(self, lake_id: int, year: int) -> bool:
        """Check if a completed lake embedding already exists."""
        sql = text("""
            SELECT 1
            FROM lake_embeddings
            WHERE lake_id = :lake_id
              AND year     = :year
              AND status   = 'completed'
            LIMIT 1
        """)
        with self._Session() as session:
            row = session.execute(sql, {
                "lake_id": lake_id,
                "year": year,
            }).fetchone()
        return row is not None

    def dispose(self) -> None:
        """Dispose of the engine connection pool."""
        self._engine.dispose()
