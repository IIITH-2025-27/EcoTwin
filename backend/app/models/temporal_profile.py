import uuid

from sqlalchemy import Column, Float, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class TemporalProfile(Base):
    """Annual indicator time-series (NDVI / NDWI / NBR) per region."""

    __tablename__ = "temporal_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    ndvi = Column(Float)
    ndwi = Column(Float)
    nbr = Column(Float)

    __table_args__ = (
        UniqueConstraint("region_id", "year", name="uq_temporal_profile_year"),
    )

    def __repr__(self) -> str:
        return f"<TemporalProfile region_id={self.region_id} year={self.year}>"
