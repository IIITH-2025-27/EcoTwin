from uuid import UUID

import structlog
from fastapi import APIRouter, Depends

from app.core.dependencies import DatabaseDep
from app.repositories.region_repository import RegionRepository
from app.schemas.report import ReportGenerateRequest, ReportResponse
from app.services.report_service import ReportService

router = APIRouter(tags=["Reports"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> ReportService:
    return ReportService(region_repo=RegionRepository(db), session=db)


@router.post("", response_model=ReportResponse)
async def generate_report(
    body: ReportGenerateRequest,
    svc: ReportService = Depends(_service),
) -> ReportResponse:
    """
    Generate a PDF ecosystem report for the given region.
    """
    return await svc.create_report_job(body)


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report_status(
    report_id: UUID,
    svc: ReportService = Depends(_service),
) -> ReportResponse:
    """Poll report generation status and retrieve the PDF download URL when complete."""
    return await svc.get_report(report_id)
