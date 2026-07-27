import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

EMBEDDING_DIM = 768


class Region(Base):
    __tablename__ = "regions"

    lake_id = Column(BigInteger, primary_key=True)
    year = Column(Integer, primary_key=True)
    center_lat = Column(Float, nullable=False)
    center_lon = Column(Float, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    status = Column(String(20), nullable=False, server_default="pending")
    error_message = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Region lake={self.lake_id} year={self.year} status={self.status}>"


class RegionFeature(Base):
    __tablename__ = "region_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)

    # NDVI – Normalized Difference Vegetation Index
    ndvi_mean = Column(Float)
    ndvi_std = Column(Float)
    ndvi_median = Column(Float)
    ndvi_min = Column(Float)
    ndvi_max = Column(Float)

    # NDWI – Normalized Difference Water Index
    ndwi_mean = Column(Float)
    ndwi_std = Column(Float)
    ndwi_median = Column(Float)
    ndwi_min = Column(Float)
    ndwi_max = Column(Float)

    # NBR – Normalized Burn Ratio
    nbr_mean = Column(Float)
    nbr_std = Column(Float)
    nbr_median = Column(Float)
    nbr_min = Column(Float)
    nbr_max = Column(Float)

    dominant_ecosystem   = Column(String(100))
    # Populated by Phase 3 of the ML pipeline (classifier.py)
    ecosystem_confidence = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("region_id", "year", name="uq_region_feature_year"),
    )

    def __repr__(self) -> str:
        return f"<RegionFeature region_id={self.region_id} year={self.year}>"
