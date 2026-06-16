from uuid import UUID

import structlog
from fastapi import APIRouter, Depends

from app.core.dependencies import DatabaseDep
from app.repositories.region_repository import RegionRepository
from app.schemas.region import RegionQueryRequest, RegionQueryResponse, RegionSummaryResponse
from app.services.region_service import RegionService

router = APIRouter(tags=["Regions"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> RegionService:
    return RegionService(region_repo=RegionRepository(db))


@router.get("/{region_id}", response_model=RegionSummaryResponse)
async def get_region(
    region_id: UUID,
    svc: RegionService = Depends(_service),
) -> RegionSummaryResponse:
    """Return region metadata + latest ecosystem indicators."""
    return await svc.get_region_summary(region_id)


@router.post("/query", response_model=RegionQueryResponse)
async def find_region_by_coordinates(
    body: RegionQueryRequest,
    svc: RegionService = Depends(_service),
) -> RegionQueryResponse:
    """Identify the nearest grid region for a given lat/lon coordinate."""
    return await svc.find_region_by_coordinates(body.lat, body.lon)
