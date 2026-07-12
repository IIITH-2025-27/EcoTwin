from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, String, text

from app.db.base import Base


class Lake(Base):
    __tablename__ = "lakes"

    lake_id = Column(BigInteger, primary_key=True)
    lake_name = Column(String(255), nullable=True, index=True)
    country = Column(String(100), nullable=False, index=True)
    area_sqkm = Column(Float, nullable=True)
    elevation = Column(Float, nullable=True)
    pour_lat = Column(Float, nullable=True)
    pour_long = Column(Float, nullable=True)
    lake_type = Column(String(100), nullable=True)
    depth_avg = Column(Float, nullable=True)
    vol_total = Column(Float, nullable=True)
    wshd_area = Column(Float, nullable=True)
    geom = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    centroid = Column(Geometry("POINT", srid=4326), nullable=True)
    state = Column(String(100), nullable=True, index=True)
    display_name = Column(String(320), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
