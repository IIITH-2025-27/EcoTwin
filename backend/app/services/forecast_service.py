from typing import List, Optional
from uuid import UUID

import structlog

from app.core.exceptions import RegionNotFoundException
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.repositories.temporal_repository import TemporalRepository
from app.schemas.forecast import ForecastHorizon, ForecastResponse

logger = structlog.get_logger(__name__)

_FORECAST_HORIZON = 5   # years ahead
_ANALOG_POOL_SIZE = 5   # top-K analogs to consider


class ForecastService:
    """
    Analog-based forecasting engine.

    Core idea: find the historical analog region whose past state most closely
    resembles the target region today, then use that analog's subsequent
    evolution as a proxy forecast for the target.
    """

    def __init__(
        self,
        region_repo: RegionRepository,
        embedding_repo: EmbeddingRepository,
        temporal_repo: TemporalRepository,
    ) -> None:
        self._region_repo = region_repo
        self._embedding_repo = embedding_repo
        self._temporal_repo = temporal_repo

    async def generate_forecast(self, region_id: UUID) -> ForecastResponse:
        region = await self._region_repo.get_by_id(region_id)
        if not region:
            raise RegionNotFoundException(str(region_id))

        target_profile = await self._temporal_repo.get_profile(region_id)
        query_record = await self._embedding_repo.get_latest(region_id)

        if not query_record:
            raise ValueError(f"No embedding found for region {region_id}")

        current_year = query_record.year

        # Search top-K analogs (excluding the region itself)
        raw_analogs, _ = await self._embedding_repo.search_similar(
            query_embedding=list(query_record.embedding),
            top_k=_ANALOG_POOL_SIZE,
            exclude_region_id=region_id,
        )

        if not raw_analogs:
            return self._fallback_forecast(region_id, current_year, target_profile)

        best = raw_analogs[0]
        best_id: UUID = best["region_id"]
        best_similarity = float(best["similarity_score"])
        analog_match_year: int = best["year"]

        analog_profile = await self._temporal_repo.get_profile(best_id)

        horizons = _project_trajectory(
            target_profile=target_profile,
            analog_profile=analog_profile,
            analog_match_year=analog_match_year,
            current_year=current_year,
            similarity_score=best_similarity,
        )

        ndvi_vals = [p.ndvi for p in target_profile if p.ndvi is not None]
        ndwi_vals = [p.ndwi for p in target_profile if p.ndwi is not None]
        nbr_vals = [p.nbr for p in target_profile if p.nbr is not None]

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
            vegetation_trend=_trend(ndvi_vals),
            water_trend=_trend(ndwi_vals),
            burn_severity_trend=_trend(nbr_vals),
            explanation=(
                f"Region in {current_year} closely resembles analog {best_id} "
                f"as it appeared in {analog_match_year} "
                f"(cosine similarity: {best_similarity:.3f}). "
                "Forecast is derived from that analog's subsequent evolution."
            ),
        )

    def _fallback_forecast(
        self,
        region_id: UUID,
        current_year: int,
        target_profile: list,
    ) -> ForecastResponse:
        last = target_profile[-1] if target_profile else None
        horizons = [
            ForecastHorizon(
                year=current_year + i,
                ndvi_forecast=round(last.ndvi or 0.0, 4) if last else 0.0,
                ndwi_forecast=round(last.ndwi or 0.0, 4) if last else 0.0,
                nbr_forecast=round(last.nbr or 0.0, 4) if last else 0.0,
                confidence=round(max(0.05, 0.3 - (i - 1) * 0.04), 3),
            )
            for i in range(1, _FORECAST_HORIZON + 1)
        ]
        ndvi_vals = [p.ndvi for p in target_profile if p.ndvi is not None]
        ndwi_vals = [p.ndwi for p in target_profile if p.ndwi is not None]
        nbr_vals = [p.nbr for p in target_profile if p.nbr is not None]
        return ForecastResponse(
            region_id=region_id,
            current_year=current_year,
            forecast_horizons=horizons,
            best_analog_id=None,
            analog_match_year=None,
            overall_confidence=0.3,
            vegetation_trend=_trend(ndvi_vals),
            water_trend=_trend(ndwi_vals),
            burn_severity_trend=_trend(nbr_vals),
            explanation="No close analog found; forecast extrapolated from own historical trend.",
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _project_trajectory(
    target_profile: list,
    analog_profile: list,
    analog_match_year: int,
    current_year: int,
    similarity_score: float,
) -> List[ForecastHorizon]:
    analog_by_year = {p.year: p for p in analog_profile}
    last_known = target_profile[-1] if target_profile else None
    horizons: List[ForecastHorizon] = []

    for offset in range(1, _FORECAST_HORIZON + 1):
        forecast_year = current_year + offset
        analog_future = analog_by_year.get(analog_match_year + offset)
        confidence = round(similarity_score * max(0.3, 1.0 - (offset - 1) * 0.08), 3)

        if analog_future:
            horizons.append(ForecastHorizon(
                year=forecast_year,
                ndvi_forecast=round(analog_future.ndvi or 0.0, 4),
                ndwi_forecast=round(analog_future.ndwi or 0.0, 4),
                nbr_forecast=round(analog_future.nbr or 0.0, 4),
                confidence=confidence,
            ))
        else:
            horizons.append(ForecastHorizon(
                year=forecast_year,
                ndvi_forecast=round(last_known.ndvi or 0.0, 4) if last_known else 0.0,
                ndwi_forecast=round(last_known.ndwi or 0.0, 4) if last_known else 0.0,
                nbr_forecast=round(last_known.nbr or 0.0, 4) if last_known else 0.0,
                confidence=round(confidence * 0.5, 3),
            ))

    return horizons


def _trend(values: List[float]) -> str:
    """Derive a simple directional trend label from a time series."""
    if len(values) < 2:
        return "stable"
    recent = values[-3:] if len(values) >= 3 else values
    slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
    if slope > 0.01:
        return "increasing"
    if slope < -0.01:
        return "declining"
    return "stable"
