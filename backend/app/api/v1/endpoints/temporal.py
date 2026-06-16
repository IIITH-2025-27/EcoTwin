from uuid import UUID

import structlog
from fastapi import APIRouter

from app.core.dependencies import DatabaseDep
from app.repositories.temporal_repository import TemporalRepository
from app.schemas.forecast import TemporalDataResponse, YearlyIndicator

router = APIRouter(tags=["Temporal"])
logger = structlog.get_logger(__name__)


@router.get("/{region_id}", response_model=TemporalDataResponse)
async def get_temporal_profile(
    region_id: UUID,
    db: DatabaseDep,
) -> TemporalDataResponse:
    """
    Return the year-by-year NDVI / NDWI / NBR time-series for a region
    (2018–present, one data point per year).
    """
    repo = TemporalRepository(db)
    profiles = await repo.get_profile(region_id)

    return TemporalDataResponse(
        region_id=region_id,
        ndvi=[
            YearlyIndicator(year=p.year, value=round(p.ndvi, 4))
            for p in profiles
            if p.ndvi is not None
        ],
        ndwi=[
            YearlyIndicator(year=p.year, value=round(p.ndwi, 4))
            for p in profiles
            if p.ndwi is not None
        ],
        nbr=[
            YearlyIndicator(year=p.year, value=round(p.nbr, 4))
            for p in profiles
            if p.nbr is not None
        ],
    )
