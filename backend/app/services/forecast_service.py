from typing import List, Optional
from uuid import UUID

import structlog

from app.core.exceptions import EmbeddingNotFoundException, RegionNotFoundException
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.forecast import (
    AnalogForecastInput,
    EmbeddingForecastResult,
    ForecastHorizon,
    ForecastResponse,
)
from app.schemas.similarity import SimilarityMethod
from app.services.forecasting_module import ForecastingModule
from app.services.similarity_service import SimilarityService

logger = structlog.get_logger(__name__)

_DEFAULT_FORECAST_HORIZON: int = 3   # years ahead
_DEFAULT_ANALOG_POOL: int = 5        # top-K analogs to try
_LEGACY_FORECAST_HORIZON: int = 5    # kept for the legacy fallback response

# Cosine/KNN on L2-normalised embeddings: scores cluster in [0.5, 1.0].
# Below 0.5 the vectors are essentially random; above 0.5 is the meaningful
# signal range.  Linear rescaling maps [floor, 1.0] → [0.0, 1.0].
_COSINE_FLOOR: float = 0.5


def _calibrate_confidence(raw_score: float, method: SimilarityMethod) -> float:
    """
    Map a raw weighted-mean similarity score to a human-meaningful confidence.

    Each similarity method has a different effective score range:

    COSINE / KNN
        Prithvi embeddings are L2-normalised before storage, so cosine
        similarity = inner product ∈ [-1, 1], clamped to [0, 1].  For any
        two ecosystems of similar type the score clusters near 1.0, making
        the raw value uninformative as a confidence indicator.
        Fix: linearly rescale [_COSINE_FLOOR, 1.0] → [0.0, 1.0].

    EUCLIDEAN
        Score = 1 / (1 + distance) ∈ (0, 1].  Distance is unbounded, so
        this metric naturally spreads across the full range.  A score of
        0.5 means distance = 1.0 (a meaningful gap); 0.9 means distance ≈ 0.11
        (a very close match).  No rescaling needed.
    """
    if method in (SimilarityMethod.COSINE, SimilarityMethod.KNN):
        span = 1.0 - _COSINE_FLOOR
        return max(0.0, min(1.0, (raw_score - _COSINE_FLOOR) / span))
    # EUCLIDEAN: already on a meaningful [0, 1] scale.
    return max(0.0, min(1.0, raw_score))


class ForecastService:
    """
    Analog-based forecasting service.

    Orchestration
    -------------
    1. Run ``SimilarityService.search_analogs`` to obtain a ranked list of
       analog trajectories for the query region.
    2. Convert the ranked results into ``AnalogForecastInput`` objects that
       carry the lake ID, matched window, similarity score, and forecast horizon.
    3. Wrap ``EmbeddingRepository.get_timeline_for_lake`` as an async callable
       and inject it into the standalone ``ForecastingModule``.
    4. Let ``ForecastingModule.run`` handle candidate filtering, weight
       computation, and weighted-average embedding generation.
    5. Map the ``EmbeddingForecastResult`` back onto the legacy
       ``ForecastResponse`` shape so the existing API contract is unchanged.
    """

    def __init__(
        self,
        region_repo: RegionRepository,
        embedding_repo: EmbeddingRepository,
        temporal_repo=None,  # kept for backwards compat; not used
    ) -> None:
        self._region_repo = region_repo
        self._embedding_repo = embedding_repo
        self._similarity_svc: Optional[SimilarityService] = None
        self._forecasting_module = ForecastingModule()

    def _get_similarity_service(self) -> SimilarityService:
        """Lazily build a SimilarityService that shares the same DB session."""
        if self._similarity_svc is None:
            self._similarity_svc = SimilarityService(
                embedding_repo=self._embedding_repo,
                region_repo=self._region_repo,
            )
        return self._similarity_svc

    async def generate_forecast(
        self,
        region_id: UUID,
        forecast_horizon: int = _DEFAULT_FORECAST_HORIZON,
        num_analogs: int = _DEFAULT_ANALOG_POOL,
        method: SimilarityMethod = SimilarityMethod.COSINE,
        year: Optional[int] = None,
    ) -> ForecastResponse:
        """
        Generate an analog-based embedding forecast for *region_id*.

        Parameters
        ----------
        region_id:
            Target region to forecast.
        forecast_horizon:
            Number of future years to predict (default: 3).
        num_analogs:
            Maximum number of valid analog trajectories to include in the
            weighted average (default: 5).
        method:
            Similarity method to use for the analog search and for weight
            computation inside the forecasting module.
        year:
            Anchor year for the query trajectory.  Defaults to the latest
            available year for the region.
        """
        region = await self._region_repo.get_by_id(region_id)
        if not region:
            raise RegionNotFoundException(str(region_id))

        # ── Step 1: Run similarity search ────────────────────────────────────
        similarity_svc = self._get_similarity_service()
        try:
            search_response = await similarity_svc.search_analogs(
                region_id=region_id,
                year=year,
                top_k=min(num_analogs * 4, 50),  # over-fetch to allow skips
                exclude_same_region=True,
                method=method,
            )
        except (RegionNotFoundException, EmbeddingNotFoundException):
            raise
        except Exception as exc:
            logger.warning("Similarity search failed in forecast", error=str(exc))
            return self._fallback_forecast(region_id, year or 2025)

        query_year: int = search_response.query_year

        if not search_response.analogs:
            logger.info(
                "No analogs returned by similarity search; using fallback",
                region_id=str(region_id),
                query_year=query_year,
            )
            return self._fallback_forecast(region_id, query_year)

        # ── Step 2: Build AnalogForecastInput list ───────────────────────────
        # We need the lake_id and matched_window_start/end for each analog.
        # SimilarityService stores the best-window information in best_matches
        # but AnalogResult currently only exposes region_id, year, similarity_score.
        # We retrieve the lake_id from the DB for each analog region.
        ranked_inputs: List[AnalogForecastInput] = []
        for analog in search_response.analogs:
            try:
                row = await self._region_repo.get_by_id_with_lake(analog.region_id)
                if row is None:
                    continue
                lake_id: int = int(row["lake_id"])
                # The similarity search returns the end year of the matched window
                # as `year`.  We back-calculate the start (window_size = 5).
                window_end: int = analog.year
                window_start: int = window_end - 4  # 5-year window
                ranked_inputs.append(
                    AnalogForecastInput(
                        lake_id=lake_id,
                        region_id=analog.region_id,
                        matched_window_start=window_start,
                        matched_window_end=window_end,
                        similarity_score=analog.similarity_score,
                        forecast_horizon=forecast_horizon,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed to build AnalogForecastInput; skipping",
                    region_id=str(analog.region_id),
                    error=str(exc),
                )

        if not ranked_inputs:
            logger.warning(
                "All analog inputs failed to build; using fallback",
                region_id=str(region_id),
            )
            return self._fallback_forecast(region_id, query_year)

        # ── Step 3: Build the embedding-lookup callable ──────────────────────
        # The forecasting module is DB-agnostic — inject the repository method.
        async def embedding_lookup(lake_id: int):
            return await self._embedding_repo.get_timeline_for_lake(lake_id)

        # ── Step 4: Run the forecasting module ───────────────────────────────
        try:
            result: EmbeddingForecastResult = await self._forecasting_module.run(
                ranked_results=ranked_inputs,
                embedding_lookup=embedding_lookup,
                query_year=query_year,
                method=method,
                desired_num_analogs=num_analogs,
            )
        except Exception as exc:
            logger.warning("ForecastingModule failed", error=str(exc))
            return self._fallback_forecast(region_id, query_year)

        # ── Step 5: Map EmbeddingForecastResult → ForecastResponse ───────────
        if result.num_analogs_used == 0 or not result.forecast_embeddings:
            return self._fallback_forecast(region_id, query_year)

        best_analog = result.selected_analogs[0]
        # Weighted-mean similarity across all selected analogs, then calibrated
        # to a method-aware scale so that each method's score range maps
        # meaningfully to [0.0, 1.0] (see _calibrate_confidence above).
        weighted_sim = sum(a.weight * a.similarity_score for a in result.selected_analogs)
        overall_confidence = round(_calibrate_confidence(weighted_sim, method), 3)

        horizons = [
            ForecastHorizon(
                year=horizon_year,
                ndvi_forecast=0.0,   # will be decoded from embedding in a later stage
                ndwi_forecast=0.0,
                nbr_forecast=0.0,
                confidence=round(
                    # Decay from the weighted-mean similarity so all analogs'
                    # agreement is reflected, not just the best analog alone.
                    overall_confidence * max(0.3, 1.0 - (offset - 1) * 0.08),
                    3,
                ),
            )
            for offset, horizon_year in enumerate(
                sorted(result.forecast_embeddings.keys()), start=1
            )
        ]

        analog_ids_str = ", ".join(
            str(a.region_id) for a in result.selected_analogs[:3]
        )
        explanation = (
            f"Region in {query_year} matched {result.num_analogs_used} analog "
            f"trajectory(ies) (method: {method.value}). "
            f"Top analogs: {analog_ids_str}. "
            "Embedding-based forecast generated; spectral indicator decoding "
            "will be available once the feature pipeline runs."
        )

        logger.info(
            "ForecastResponse assembled",
            region_id=str(region_id),
            query_year=query_year,
            num_analogs_used=result.num_analogs_used,
            forecast_years=sorted(result.forecast_embeddings.keys()),
        )

        return ForecastResponse(
            region_id=region_id,
            current_year=query_year,
            forecast_horizons=horizons,
            best_analog_id=best_analog.region_id,
            analog_match_year=best_analog.matched_window_end,
            overall_confidence=max(0.0, min(1.0, overall_confidence)),
            vegetation_trend="stable",
            water_trend="stable",
            burn_severity_trend="stable",
            explanation=explanation,
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
            for i in range(1, _LEGACY_FORECAST_HORIZON + 1)
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
