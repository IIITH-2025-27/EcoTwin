"""SQLAlchemy model for the lake_tiles metadata table."""

from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2 import Geometry
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


class LakeTile(Base):
    """Tracks individual 10 km × 10 km Sentinel-2 GeoTIFF tiles per lake per year."""

    __tablename__ = "lake_tiles"
    __table_args__ = (
        UniqueConstraint(
            "lake_id", "year", "tile_index", name="uq_lake_tiles_lake_year_tile"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lake_id = Column(BigInteger, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    tile_index = Column(String(20), nullable=False)  # e.g. "0_0", "1_2"
    tile_geometry = Column(
        Geometry("POLYGON", srid=4326), nullable=True
    )
    bbox = Column(String(200), nullable=True)  # "west,south,east,north"
    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    image_path = Column(Text, nullable=True)
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
