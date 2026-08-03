from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CacheDep, DatabaseDep
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.forecast import EcologicalForecastResponse, ForecastResponse
from app.schemas.similarity import SimilarityMethod
from app.services.ecological_forecast_service import EcologicalForecastService
from app.services.forecast_service import ForecastService

router = APIRouter(tags=["Forecast"])
logger = structlog.get_logger(__name__)


def _service(db: DatabaseDep) -> ForecastService:
    return ForecastService(
        region_repo=RegionRepository(db),
        embedding_repo=EmbeddingRepository(db),
    )


def _eco_service(db: DatabaseDep) -> EcologicalForecastService:
    return EcologicalForecastService(
        session=db,
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


@router.get("/ecological/{region_id}", response_model=EcologicalForecastResponse)
async def get_ecological_forecast(
    region_id: UUID,
    year: Optional[int] = Query(
        None,
        description="Anchor year for the query trajectory (defaults to latest).",
    ),
    num_analogs: int = Query(
        5, ge=1, le=20,
        description="Maximum number of twin lake trajectories to use.",
    ),
    method: SimilarityMethod = Query(
        SimilarityMethod.COSINE,
        description="Embedding similarity method for twin search.",
    ),
    cache: CacheDep = None,
    svc: EcologicalForecastService = Depends(_eco_service),
) -> EcologicalForecastResponse:
    """
    Generate an ecological index forecast for a region.

    Uses embedding-based similarity search to find twin lakes, then
    extracts directional trends (NDCI, NDVI-B7, Turbidity Ratio,
    Red Edge Slope) from those twins' future index values and projects
    them onto the target lake's current indices.

    Returns per-index trend direction, magnitude, projections, and
    full twin traceability for auditability.
    """
    cache_key = (
        f"eco_forecast:{region_id}:{year}:{num_analogs}:{method.value}"
    )

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return EcologicalForecastResponse.model_validate_json(cached)

    result = await svc.generate_ecological_forecast(
        region_id=region_id,
        year=year,
        num_analogs=num_analogs,
        method=method,
    )

    if cache:
        await cache.set(cache_key, result.model_dump_json())

    return result
