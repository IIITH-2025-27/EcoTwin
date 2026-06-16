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
            status=ReportStatus.PENDING,
        )
        self._session.add(report)
        await self._session.flush()
        await self._session.refresh(report)

        # Dispatch async Celery task
        from app.workers.tasks.report_tasks import generate_report_task  # noqa: PLC0415

        task = generate_report_task.delay(
            str(report.report_id),
            str(request.region_id),
            request.include_forecast,
            request.include_analogs,
            request.top_k_analogs,
        )

        report.celery_task_id = task.id
        report.status = ReportStatus.PROCESSING
        await self._session.flush()

        logger.info(
            "Report job created",
            report_id=str(report.report_id),
            celery_task=task.id,
        )
        return ReportResponse.model_validate(report)

    async def get_report(self, report_id: UUID) -> ReportResponse:
        result = await self._session.execute(
            select(Report).where(Report.report_id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise ReportNotFoundException(str(report_id))
        return ReportResponse.model_validate(report)
