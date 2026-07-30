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
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
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
