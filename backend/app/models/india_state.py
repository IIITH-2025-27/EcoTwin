from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, Integer, String

from app.db.base import Base


class IndiaState(Base):
    """Administrative state/union-territory boundaries used for lake attribution."""

    __tablename__ = "india_states"

    id = Column(Integer, primary_key=True)
    state_name = Column(String(100), nullable=False, unique=True, index=True)
    geom = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
