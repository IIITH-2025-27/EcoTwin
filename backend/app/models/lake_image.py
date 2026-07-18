"""SQLAlchemy model for the lake_images metadata table."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.base import Base


class LakeImage(Base):
    """Tracks downloaded Sentinel-2 GeoTIFF files per lake per year."""

    __tablename__ = "lake_images"
    __table_args__ = (
        UniqueConstraint("lake_id", "year", name="uq_lake_images_lake_year"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lake_id = Column(BigInteger, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    file_path = Column(String(512), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    file_size_bytes = Column(BigInteger, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
