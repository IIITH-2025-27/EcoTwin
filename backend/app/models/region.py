import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

EMBEDDING_DIM = 768


class Region(Base):
    """One embedding record per lake per year (the regions table stores lake-year embeddings)."""

    __tablename__ = "regions"

    region_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lake_id = Column(
        BigInteger,
        ForeignKey("lakes.lake_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    center_lat = Column(Float, nullable=False)
    center_lon = Column(Float, nullable=False)
    # Single vector used by similarity and forecasting:
    #   normalize(lake_weight · lake_embedding + (1 − lake_weight) · shore_embedding)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    # Parts kept so the blend can be re-tuned without re-running Prithvi
    lake_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    shore_embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    lake_weight = Column(Float, nullable=True)
    lake_token_weight = Column(Float, nullable=True)   # Σ valid-lake token fractions
    shore_token_weight = Column(Float, nullable=True)  # Σ valid-shore token fractions
    tokens_encoded = Column(Integer, nullable=True)
    # 1 = legacy 1 km cells (10 m, B2-B7); 2 = lake + shore tokens (30 m)
    embedding_version = Column(Integer, nullable=False, server_default="1")
    status = Column(String(20), nullable=False, server_default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("lake_id", "year", name="uq_regions_lake_year"),
    )

    def __repr__(self) -> str:
        return f"<Region region_id={self.region_id} lake={self.lake_id} year={self.year} status={self.status}>"
