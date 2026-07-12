import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base

EMBEDDING_DIM = 768


class SubRegion(Base):
    """A valid 1 km lake grid cell for one processing year."""

    __tablename__ = "sub_regions"

    sub_region_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lake_id = Column(BigInteger, ForeignKey("lakes.lake_id", ondelete="CASCADE"), nullable=False)
    cell_number = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    coverage_percent = Column(Float, nullable=False)
    center_lat = Column(Float, nullable=False)
    center_lon = Column(Float, nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    features = relationship(
        "SubRegionFeature", back_populates="sub_region", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("lake_id", "cell_number", "year", name="uq_sub_region_lake_cell_year"),
    )


class SubRegionFeature(Base):
    """Spectral features calculated for one valid lake grid cell."""

    __tablename__ = "sub_region_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sub_region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sub_regions.sub_region_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    ndvi_mean = Column(Float)
    ndvi_std = Column(Float)
    ndvi_median = Column(Float)
    ndvi_min = Column(Float)
    ndvi_max = Column(Float)
    ndwi_mean = Column(Float)
    ndwi_std = Column(Float)
    ndwi_median = Column(Float)
    ndwi_min = Column(Float)
    ndwi_max = Column(Float)
    nbr_mean = Column(Float)
    nbr_std = Column(Float)
    nbr_median = Column(Float)
    nbr_min = Column(Float)
    nbr_max = Column(Float)
    dominant_ecosystem = Column(String(100))
    ecosystem_confidence = Column(Float, nullable=True)

    sub_region = relationship("SubRegion", back_populates="features")

    __table_args__ = (
        UniqueConstraint("sub_region_id", "year", name="uq_sub_region_feature_year"),
    )
