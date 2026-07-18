"""SQLAlchemy model for aggregated lake-level Prithvi embeddings."""

from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint

from app.db.base import Base

EMBEDDING_DIM = 768


class LakeEmbedding(Base):
    """Weighted-mean-pooled Prithvi embedding for an entire lake in one year."""

    __tablename__ = "lake_embeddings"
    __table_args__ = (
        UniqueConstraint("lake_id", "year", name="uq_lake_embedding_lake_year"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lake_id = Column(BigInteger, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    num_cells = Column(Integer, nullable=False, default=0)
    status = Column(
        String(20), nullable=False, default="completed", server_default="completed"
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
