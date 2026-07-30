from uuid import UUID

import structlog
from fastapi import APIRouter

from app.core.dependencies import DatabaseDep
from app.schemas.forecast import TemporalDataResponse

router = APIRouter(tags=["Temporal"])
logger = structlog.get_logger(__name__)


@router.get("/{region_id}", response_model=TemporalDataResponse)
async def get_temporal_profile(
    region_id: UUID,
    db: DatabaseDep,
) -> TemporalDataResponse:
    """
    Return the year-by-year NDVI / NDWI / NBR time-series for a region.
    Currently returns empty series until the region_features table is populated.
    """
    logger.info("Temporal profile requested", region_id=str(region_id))
    return TemporalDataResponse(
        region_id=region_id,
        ndvi=[],
        ndwi=[],
        nbr=[],
    )
