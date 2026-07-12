import asyncio
import uuid
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.exceptions import RegionNotFoundException, ReportNotFoundException
from app.models.report import Report, ReportStatus
from app.repositories.region_repository import RegionRepository
from app.schemas.report import ReportGenerateRequest, ReportResponse

logger = structlog.get_logger(__name__)


class ReportService:
    def __init__(self, region_repo: RegionRepository, session: AsyncSession) -> None:
        self._region_repo = region_repo
        self._session = session

    async def create_report_job(self, request: ReportGenerateRequest) -> ReportResponse:
        region = await self._region_repo.get_by_id(request.region_id)
        if not region:
            raise RegionNotFoundException(str(request.region_id))

        report = Report(
            report_id=uuid.uuid4(),
            region_id=request.region_id,
            status=ReportStatus.PROCESSING,
        )
        self._session.add(report)
        await self._session.flush()

        from app.services.report_generator import build_pdf, persist_pdf

        try:
            pdf_bytes = await asyncio.to_thread(
                build_pdf,
                str(report.report_id),
                str(request.region_id),
                request.include_forecast,
                request.include_analogs,
            )
            report.pdf_url = await asyncio.to_thread(
                persist_pdf, str(report.report_id), pdf_bytes
            )
            report.status = ReportStatus.COMPLETED
            logger.info("Report generation completed", report_id=str(report.report_id))
        except Exception as exc:
            report.status = ReportStatus.FAILED
            report.error_message = str(exc)
            logger.exception("Report generation failed", report_id=str(report.report_id))

        await self._session.flush()
        return ReportResponse.model_validate(report)

    async def get_report(self, report_id: UUID) -> ReportResponse:
        result = await self._session.execute(
            select(Report).where(Report.report_id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise ReportNotFoundException(str(report_id))
        return ReportResponse.model_validate(report)
