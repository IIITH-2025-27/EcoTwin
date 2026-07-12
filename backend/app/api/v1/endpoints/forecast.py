from uuid import UUID

import structlog
from fastapi import APIRouter, Depends

from app.core.dependencies import CacheDep, DatabaseDep
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.repositories.temporal_repository import TemporalRepository
from app.schemas.forecast import ForecastResponse
from app.services.forecast_service import ForecastService

router = APIRouter(tags=["Forecast"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> ForecastService:
    return ForecastService(
        region_repo=RegionRepository(db),
        embedding_repo=EmbeddingRepository(db),
        temporal_repo=TemporalRepository(db),
    )


@router.get("/{region_id}", response_model=ForecastResponse)
async def get_ecosystem_forecast(
    region_id: UUID,
    cache: CacheDep = None,
    svc: ForecastService = Depends(_service),
) -> ForecastResponse:
    """
    Generate a 5-year analog-based ecosystem forecast for a region.
    Returns predicted NDVI / NDWI / NBR trajectories with per-year confidence scores.
    """
    cache_key = f"forecast:{region_id}"

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return ForecastResponse.model_validate_json(cached)

    result = await svc.generate_forecast(region_id)

    if cache:
        await cache.set(cache_key, result.model_dump_json())

    return result
