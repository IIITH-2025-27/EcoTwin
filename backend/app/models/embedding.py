import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base

EMBEDDING_DIM = 768


class RegionEmbedding(Base):
    """768-dimensional Prithvi foundation model embedding per region per year."""

    __tablename__ = "region_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.region_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)

    region = relationship("Region", back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint("region_id", "year", name="uq_region_embedding_year"),
    )

    def __repr__(self) -> str:
        return f"<RegionEmbedding region_id={self.region_id} year={self.year}>"
