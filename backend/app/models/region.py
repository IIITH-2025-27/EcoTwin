import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Region(Base):
    __tablename__ = "regions"

    region_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    center_lat = Column(Float, nullable=False)
    center_lon = Column(Float, nullable=False)
    area_km = Column(Float, default=25.0)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    features = relationship(
        "RegionFeature", back_populates="region", cascade="all, delete-orphan"
    )
    embeddings = relationship(
        "RegionEmbedding", back_populates="region", cascade="all, delete-orphan"
    )
    temporal_profiles = relationship(
        "TemporalProfile", back_populates="region", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="region", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Region id={self.region_id} lat={self.center_lat} lon={self.center_lon}>"


class RegionFeature(Base):
    __tablename__ = "region_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.region_id", ondelete="CASCADE"),
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

    dominant_ecosystem = Column(String(100))

    region = relationship("Region", back_populates="features")

    __table_args__ = (
        UniqueConstraint("region_id", "year", name="uq_region_feature_year"),
    )

    def __repr__(self) -> str:
        return f"<RegionFeature region_id={self.region_id} year={self.year}>"
