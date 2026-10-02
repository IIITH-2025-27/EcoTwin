"""
Analog-based Embedding Forecasting Module
==========================================
This module is **completely independent** of the similarity search implementation.
It only consumes the ranked similarity results produced by ``SimilarityService``
and the per-lake historical embeddings it fetches itself via ``EmbeddingRepository``.

Algorithm
---------
1. Accept the full ranked list of ``AnalogForecastInput`` objects, already sorted
   in descending order of similarity (best first).
2. Iterate through the list and, for each candidate, verify that the lake's
   embedding timeline contains at least ``forecast_horizon`` years *after* the
   matched window.  Skip any candidate that does not meet this requirement.
3. Collect valid analogs until ``desired_num_analogs`` are found, or the ranked
   list is exhausted — whichever comes first.  Proceed with however many valid
   analogs were found; never raise an error due to insufficient analogs.
4. Compute per-analog weights from the raw similarity scores using a strategy
   determined by the ``SimilarityMethod`` supplied at call time:
     - ``COSINE``   : scores are already in [0, 1]; normalise to sum-to-one.
     - ``EUCLIDEAN``: convert ``distance -> 1/(1+distance)`` then normalise.
     - ``KNN``      : when distances are available apply the same conversion as
                      EUCLIDEAN; otherwise assign equal weights.
5. For each horizon year (1 ... ``forecast_horizon``) compute the weighted average
   of the future embeddings across all selected analogs and store the result.
6. Return an ``EmbeddingForecastResult`` containing the per-year forecast
   embeddings and the full analog metadata (lake ID, matched window, similarity
   score, weight, and count).

Extensibility
-------------
Weight computation is delegated to a single factory method
``_compute_weights(analogs, method)`` so that new similarity methods can be
supported by adding an ``elif`` branch there — no changes are needed elsewhere
in the pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Coroutine, Dict, List, Optional, Tuple
from uuid import UUID

import structlog

from app.schemas.forecast import (
    AnalogForecastInput,
    EmbeddingForecastResult,
    SelectedAnalog,
)
from app.schemas.similarity import SimilarityMethod

logger = structlog.get_logger(__name__)

# Default number of analog trajectories to select when not specified.
_DEFAULT_NUM_ANALOGS = 5


# ---------------------------------------------------------------------------
# Type alias for the embedding-lookup callable injected by the caller.
# Signature: async (lake_id: int) -> List[Tuple[int, List[float]]]
#   Returns a time-ordered list of (year, embedding) pairs for the lake.
# ---------------------------------------------------------------------------
EmbeddingLookup = Callable[[int], Coroutine[None, None, List[Tuple[int, List[float]]]]]


# ---------------------------------------------------------------------------
# Weight computation — modular by design
# ---------------------------------------------------------------------------

def _distance_to_similarity(distance: float) -> float:
    """Convert a non-negative Euclidean/KNN distance to a similarity score."""
    return 1.0 / (1.0 + distance)


def _normalize(values: List[float]) -> List[float]:
    """Return *values* re-scaled so they sum to one.  Falls back to equal weights."""
    total = sum(values)
    if total <= 0.0:
        n = len(values)
        return [1.0 / n] * n if n else []
    return [v / total for v in values]


def _compute_weights(
    candidates: List[Tuple[AnalogForecastInput, Optional[float]]],
    method: SimilarityMethod,
) -> List[float]:
    """
    Compute normalised contribution weights for every selected analog.

    Parameters
    ----------
    candidates:
        A list of ``(AnalogForecastInput, raw_distance_or_None)`` tuples.
        ``raw_distance_or_None`` is ``None`` for COSINE (no distance needed)
        and for KNN when no explicit distance is available.
    method:
        The similarity method used during the search.

    Returns
    -------
    List of weights in the same order as *candidates*, summing to 1.0.
    """
    if method == SimilarityMethod.COSINE:
        # Scores from cosine search are already in [0, 1].
        raw = [c.similarity_score for c, _ in candidates]
        return _normalize(raw)

    if method == SimilarityMethod.EUCLIDEAN:
        # similarity_score was stored as 1/(1+d); recover distance then re-derive sim.
        # We re-derive explicitly to keep the formula auditable.
        raw = [
            _distance_to_similarity(1.0 / max(c.similarity_score, 1e-9) - 1.0)
            for c, _ in candidates
        ]
        return _normalize(raw)

    if method == SimilarityMethod.KNN:
        distances = [dist for _, dist in candidates]
        if all(d is not None for d in distances):
            raw = [_distance_to_similarity(d) for d in distances]  # type: ignore[arg-type]
            return _normalize(raw)
        # No explicit distances available — fall through to equal weights.

    # Default: equal weights (covers unknown methods and KNN without distances).
    n = len(candidates)
    return [1.0 / n] * n if n else []


# ---------------------------------------------------------------------------
# Core forecasting logic
# ---------------------------------------------------------------------------

def _weighted_average_embedding(
    embeddings: List[List[float]],
    weights: List[float],
) -> List[float]:
    """Return the element-wise weighted average of *embeddings*."""
    if not embeddings:
        return []
    dim = len(embeddings[0])
    result = [0.0] * dim
    for emb, w in zip(embeddings, weights):
        for i, val in enumerate(emb):
            result[i] += w * val
    return result


class ForecastingModule:
    """
    Stateless analog-based forecasting engine.

    This class **only** depends on:
    - The ranked similarity results (``List[AnalogForecastInput]``)
    - An async callable that retrieves ``(year, embedding)`` pairs for a given
      ``lake_id``  (injected by ``ForecastService``; never imported here).

    It does **not** import or reference ``SimilarityService``.
    """

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    async def run(
        self,
        ranked_results: List[AnalogForecastInput],
        embedding_lookup: EmbeddingLookup,
        query_year: int,
        method: SimilarityMethod = SimilarityMethod.COSINE,
        desired_num_analogs: int = _DEFAULT_NUM_ANALOGS,
    ) -> EmbeddingForecastResult:
        """
        Execute the full forecasting pipeline.

        Parameters
        ----------
        ranked_results:
            Complete ranked list from the similarity search, ordered best-first.
            Each element carries ``lake_id``, ``matched_window_start/end``,
            ``similarity_score``, and ``forecast_horizon``.
        embedding_lookup:
            Async callable ``(lake_id) -> List[(year, embedding)]`` used to
            retrieve future embeddings for each candidate analog.
        query_year:
            The current year of the query lake.  Forecast output years are
            labelled as ``query_year + 1``, ``query_year + 2``, …  This
            ensures the horizon years are always in the future relative to
            the query lake, regardless of when the analog windows end.
        method:
            The similarity method that produced *ranked_results*; governs how
            weights are computed.
        desired_num_analogs:
            Target number of valid analogs to collect.  If fewer valid analogs
            exist, the forecast proceeds with however many are available.

        Returns
        -------
        ``EmbeddingForecastResult`` with per-horizon forecast embeddings and
        full analog metadata.
        """
        # -- 1. Sort results best-first (defensive; callers should pre-sort) --
        sorted_results = sorted(
            ranked_results, key=lambda r: r.similarity_score, reverse=True
        )

        # -- 2. Batch-prefetch lake timelines ──────────────────────────────────
        # Collect unique lake IDs from the top candidates, fetch all in parallel.
        prefetch_candidates = sorted_results[:desired_num_analogs * 2]
        unique_lake_ids = list({c.lake_id for c in prefetch_candidates})

        async def _safe_lookup(lid: int):
            try:
                return lid, await embedding_lookup(lid)
            except Exception as exc:
                logger.warning(
                    "Embedding lookup failed for lake; skipping",
                    lake_id=lid, error=str(exc),
                )
                return lid, None

        fetch_results = await asyncio.gather(
            *[_safe_lookup(lid) for lid in unique_lake_ids]
        )
        lake_cache: Dict[int, List[Tuple[int, List[float]]]] = {
            lid: sorted(tl, key=lambda t: t[0])
            for lid, tl in fetch_results
            if tl is not None
        }

        # -- 3. Select valid analogs from prefetched data ─────────────────────
        ValidEntry = Tuple[AnalogForecastInput, List[Tuple[int, List[float]]]]
        valid: List[ValidEntry] = []

        for candidate in sorted_results:
            if len(valid) >= desired_num_analogs:
                break

            lake_id = candidate.lake_id
            horizon = candidate.forecast_horizon

            timeline = lake_cache.get(lake_id)
            if timeline is None:
                continue

            # Verify there are enough future embeddings
            future = [
                (yr, emb)
                for yr, emb in timeline
                if yr > candidate.matched_window_end
            ]
            if len(future) < horizon:
                logger.debug(
                    "Analog skipped: insufficient future embeddings",
                    lake_id=lake_id,
                    matched_window_end=candidate.matched_window_end,
                    available_future=len(future),
                    required_horizon=horizon,
                )
                continue

            valid.append((candidate, timeline))
            logger.debug(
                "Analog selected",
                lake_id=lake_id,
                matched_window_end=candidate.matched_window_end,
                future_years_available=len(future),
            )

        if not valid:
            logger.warning(
                "No valid analogs found; returning empty forecast",
                num_candidates_examined=len(sorted_results),
            )
            return EmbeddingForecastResult(
                forecast_embeddings={},
                selected_analogs=[],
                num_analogs_used=0,
                forecast_horizon=sorted_results[0].forecast_horizon if sorted_results else 0,
            )

        # -- 4. Compute weights -----------------------------------------------
        # For EUCLIDEAN and KNN we pass the raw distance alongside the input;
        # since similarity_score already encodes the distance (1/(1+d) or inner
        # product), we pass None and let _compute_weights recover it from the score.
        candidates_for_weighting: List[Tuple[AnalogForecastInput, Optional[float]]] = [
            (analog_input, None) for analog_input, _ in valid
        ]
        weights = _compute_weights(candidates_for_weighting, method)

        logger.info(
            "Weights computed",
            method=method.value,
            num_analogs=len(valid),
            weights=[round(w, 4) for w in weights],
        )

        # -- 5. Pre-compute future embeddings per analog ──────────────────────
        horizon = valid[0][0].forecast_horizon
        forecast_embeddings: Dict[int, List[float]] = {}

        # Pre-sort future embeddings once per analog to avoid repeated sorting
        precomputed_futures: List[Tuple[List[Tuple[int, List[float]]], float]] = []
        for (analog_input, timeline), w in zip(valid, weights):
            future_sorted = sorted(
                [(yr, emb) for yr, emb in timeline if yr > analog_input.matched_window_end],
                key=lambda t: t[0],
            )
            precomputed_futures.append((future_sorted, w))

        for offset in range(1, horizon + 1):
            year_embeddings: List[List[float]] = []
            year_weights: List[float] = []

            for future_sorted, w in precomputed_futures:
                if offset - 1 < len(future_sorted):
                    _, emb = future_sorted[offset - 1]
                    year_embeddings.append(emb)
                    year_weights.append(w)

            if year_embeddings:
                normalised = _normalize(year_weights)
                forecast_year = query_year + offset
                forecast_embeddings[forecast_year] = _weighted_average_embedding(
                    year_embeddings, normalised
                )

        # -- 6. Build result metadata -----------------------------------------
        selected_analogs = [
            SelectedAnalog(
                lake_id=analog_input.lake_id,
                region_id=analog_input.region_id,
                matched_window_start=analog_input.matched_window_start,
                matched_window_end=analog_input.matched_window_end,
                similarity_score=analog_input.similarity_score,
                weight=round(w, 6),
            )
            for (analog_input, _), w in zip(valid, weights)
        ]

        logger.info(
            "Forecast embeddings generated",
            num_analogs_used=len(valid),
            forecast_horizon=horizon,
            horizon_years=list(forecast_embeddings.keys()),
        )

        return EmbeddingForecastResult(
            forecast_embeddings=forecast_embeddings,
            selected_analogs=selected_analogs,
            num_analogs_used=len(valid),
            forecast_horizon=horizon,
        )
