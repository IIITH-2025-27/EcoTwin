import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ReportStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base):
    __tablename__ = "reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(
        UUID(as_uuid=True),
        ForeignKey("regions.region_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    pdf_url = Column(Text, nullable=True)
    status = Column(
        Enum(ReportStatus, name="report_status_enum"),
        default=ReportStatus.PENDING,
        nullable=False,
    )
    error_message = Column(Text, nullable=True)

    region = relationship("Region", back_populates="reports")

    def __repr__(self) -> str:
        return (
            f"<Report report_id={self.report_id} "
            f"region_id={self.region_id} status={self.status}>"
        )
