from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CacheDep, DatabaseDep
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.forecast import ForecastResponse
from app.schemas.similarity import SimilarityMethod
from app.services.forecast_service import ForecastService

router = APIRouter(tags=["Forecast"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> ForecastService:
    return ForecastService(
        region_repo=RegionRepository(db),
        embedding_repo=EmbeddingRepository(db),
    )


@router.get("/{region_id}", response_model=ForecastResponse)
async def get_ecosystem_forecast(
    region_id: UUID,
    year: Optional[int] = Query(None, description="Anchor year for the query trajectory (defaults to latest)"),
    forecast_horizon: int = Query(3, ge=1, le=10, description="Number of future years to forecast"),
    num_analogs: int = Query(5, ge=1, le=20, description="Maximum number of valid analog trajectories to use"),
    method: SimilarityMethod = Query(
        SimilarityMethod.COSINE,
        description="Vector similarity method used for analog search and weight computation.",
    ),
    cache: CacheDep = None,
    svc: ForecastService = Depends(_service),
) -> ForecastResponse:
    """
    Generate an analog-based ecosystem forecast for a region.

    Runs the full pipeline: similarity search → candidate filtering →
    weighted-average embedding aggregation → ForecastResponse.
    Returns predicted NDVI / NDWI / NBR trajectories with per-year confidence scores.
    """
    cache_key = f"forecast:{region_id}:{year}:{forecast_horizon}:{num_analogs}:{method.value}"

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return ForecastResponse.model_validate_json(cached)

    result = await svc.generate_forecast(
        region_id=region_id,
        year=year,
        forecast_horizon=forecast_horizon,
        num_analogs=num_analogs,
        method=method,
    )

    if cache:
        await cache.set(cache_key, result.model_dump_json())

    return result
