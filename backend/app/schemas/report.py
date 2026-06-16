from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.report import ReportStatus


class ReportGenerateRequest(BaseModel):
    region_id: UUID
    include_forecast: bool = True
    include_analogs: bool = True
    top_k_analogs: int = Field(default=5, ge=1, le=20)


class ReportResponse(BaseModel):
    report_id: UUID
    region_id: UUID
    status: ReportStatus
    generated_at: datetime
    pdf_url: Optional[str] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}
