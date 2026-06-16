from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.dependencies import DatabaseDep
from app.repositories.region_repository import RegionRepository
from app.schemas.region import RegionQueryRequest, RegionQueryResponse, RegionSummaryResponse
from app.services.region_service import RegionService

router = APIRouter(tags=["Regions"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> RegionService:
    return RegionService(region_repo=RegionRepository(db))


@router.get("/synced-states", response_model=list[str])
async def get_synced_states(db: DatabaseDep) -> list[str]:
    """Return state names that have at least one region with pipeline data."""
    result = await db.execute(
        text(
            "SELECT DISTINCT r.state_name "
            "FROM regions r "
            "JOIN region_features rf ON rf.region_id = r.region_id "
            "WHERE r.state_name IS NOT NULL AND r.state_name != ''"
        )
    )
    return [row[0] for row in result.fetchall()]


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
