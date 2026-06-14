import uuid

from sqlalchemy import Column, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class TemporalProfile(Base):
    """Annual indicator time-series (NDVI / NDWI / NBR) per region."""

    __tablename__ = "temporal_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.region_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    ndvi = Column(Float)
    ndwi = Column(Float)
    nbr = Column(Float)

    region = relationship("Region", back_populates="temporal_profiles")

    __table_args__ = (
        UniqueConstraint("region_id", "year", name="uq_temporal_profile_year"),
    )

    def __repr__(self) -> str:
        return f"<TemporalProfile region_id={self.region_id} year={self.year}>"
