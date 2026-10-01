"""SQLAlchemy model for the pipeline_permissions table."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PipelinePermission(Base):
    """Stores per-action permission flags for data-pipeline operations."""

    __tablename__ = "pipeline_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    permission_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="FALSE"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<PipelinePermission(key={self.permission_key!r}, "
            f"enabled={self.is_enabled})>"
        )
