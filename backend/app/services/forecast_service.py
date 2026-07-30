from typing import List, Optional
from uuid import UUID

import structlog

from app.core.exceptions import RegionNotFoundException
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.forecast import ForecastHorizon, ForecastResponse

logger = structlog.get_logger(__name__)

_FORECAST_HORIZON = 5   # years ahead
_ANALOG_POOL_SIZE = 5   # top-K analogs to consider


class ForecastService:
    """
    Analog-based forecasting engine.

    Uses the most recent embedding to find similar historical regions,
    then projects their subsequent evolution as a proxy forecast.
    Since NDVI/NDWI/NBR feature tables are not yet populated, the forecast
    currently returns trend placeholders based on available embedding data.
    """

    def __init__(
        self,
        region_repo: RegionRepository,
        embedding_repo: EmbeddingRepository,
        temporal_repo=None,  # kept for backwards compat; not used
    ) -> None:
        self._region_repo = region_repo
        self._embedding_repo = embedding_repo

    async def generate_forecast(self, region_id: UUID) -> ForecastResponse:
        region = await self._region_repo.get_by_id(region_id)
        if not region:
            raise RegionNotFoundException(str(region_id))

        query_record = await self._embedding_repo.get_latest(region_id)
        if not query_record:
            return self._fallback_forecast(region_id, 2025)

        current_year = query_record.year

        # Parse the embedding safely
        parsed_embedding = EmbeddingRepository._parse_embedding(query_record.embedding)
        if not parsed_embedding:
            return self._fallback_forecast(region_id, current_year)

        # Search top-K analogs (excluding the region itself)
        try:
            raw_analogs, _ = await self._embedding_repo.search_similar(
                query_embedding=parsed_embedding,
                top_k=_ANALOG_POOL_SIZE,
                exclude_region_id=region_id,
            )
        except Exception as exc:
            logger.warning("Analog search failed in forecast", error=str(exc))
            raw_analogs = []

        if not raw_analogs:
            return self._fallback_forecast(region_id, current_year)

        best = raw_analogs[0]
        best_id: UUID = best["region_id"]
        best_similarity = float(best["similarity_score"])
        analog_match_year: int = best["year"]

        # Build horizons: we don't have NDVI/NDWI/NBR yet, so use placeholder 0.0
        horizons = [
            ForecastHorizon(
                year=current_year + offset,
                ndvi_forecast=0.0,
                ndwi_forecast=0.0,
                nbr_forecast=0.0,
                confidence=round(best_similarity * max(0.3, 1.0 - (offset - 1) * 0.08), 3),
            )
            for offset in range(1, _FORECAST_HORIZON + 1)
        ]

        logger.info(
            "Forecast generated",
            region_id=str(region_id),
            analog_id=str(best_id),
            analog_match_year=analog_match_year,
            similarity=round(best_similarity, 3),
        )

        return ForecastResponse(
            region_id=region_id,
            current_year=current_year,
            forecast_horizons=horizons,
            best_analog_id=best_id,
            analog_match_year=analog_match_year,
            overall_confidence=round(best_similarity * 0.8 + 0.2, 3),
            vegetation_trend="stable",
            water_trend="stable",
            burn_severity_trend="stable",
            explanation=(
                f"Region in {current_year} closely resembles analog {best_id} "
                f"as it appeared in {analog_match_year} "
                f"(cosine similarity: {best_similarity:.3f}). "
                "Spectral indicator forecasts will be available once the feature pipeline runs."
            ),
        )

    def _fallback_forecast(
        self,
        region_id: UUID,
        current_year: int,
    ) -> ForecastResponse:
        horizons = [
            ForecastHorizon(
                year=current_year + i,
                ndvi_forecast=0.0,
                ndwi_forecast=0.0,
                nbr_forecast=0.0,
                confidence=round(max(0.05, 0.3 - (i - 1) * 0.04), 3),
            )
            for i in range(1, _FORECAST_HORIZON + 1)
        ]
        return ForecastResponse(
            region_id=region_id,
            current_year=current_year,
            forecast_horizons=horizons,
            best_analog_id=None,
            analog_match_year=None,
            overall_confidence=0.3,
            vegetation_trend="stable",
            water_trend="stable",
            burn_severity_trend="stable",
            explanation="No close analog found or embedding data unavailable; forecast unavailable.",
        )
