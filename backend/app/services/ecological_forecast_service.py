"""Ecological index-based forecasting service.

Uses the *existing* Prithvi embedding similarity search to find twin lakes,
reads band means from ``lake_features`` (source of truth), computes ecological
indices on-the-fly, and produces a **per-year directional forecast**.

Weighting
---------
Fixed rank-based weights, not recalculated per year:
  Rank 1 = 0.28,  Rank 2 = 0.24,  Rank 3 = 0.20,
  Rank 4 = 0.16,  Rank 5 = 0.12

If a twin has no data for a given forecast year, its weight becomes **0** for
that year (excluded, not redistributed to other twins).

Classification
--------------
For each index and each forecast year, compute a weighted score:
  ``score = Σ (rank_weight × delta)``  for all twins that have data.

Then classify:
  * score >  +threshold  →  **up** (↑)
  * score <  −threshold  →  **down** (↓)
  * |score| ≤  threshold  →  **stable** (→)  — current state holds
  * < 2 twins contribute  →  **uncertain** (?) — distinct from stable

Output
------
3-year forecast table per lake, one row per index, direction per year.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.forecast import (
    EcologicalForecastResponse,
    ForecastAuditReport,
    IndexForecast,
    TwinContribution,
    TwinDeltaContribution,
    YearlyDirection,
)
from app.schemas.similarity import SimilarityMethod
from app.services.index_calculator import compute_ecological_indices
from app.services.similarity_service import SimilarityService

logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Fixed rank-based weights (1-indexed rank → weight)
_RANK_WEIGHTS: Dict[int, float] = {
    1: 0.28,
    2: 0.24,
    3: 0.20,
    4: 0.16,
    5: 0.12,
}

# Classification threshold — weighted score above/below this → up/down
_DIRECTION_THRESHOLD: float = 0.005

# Minimum twins contributing for a year to avoid "uncertain"
_MIN_TWINS_FOR_DIRECTION: int = 2

# Forecast horizon (years into the future)
_FORECAST_HORIZON: int = 3

_INDEX_KEYS: List[str] = ["ndci", "ndvi_b7", "ndwi", "turbidity_ratio", "red_edge_slope"]

_INDEX_LABELS: Dict[str, str] = {
    "ndci": "NDCI (Chlorophyll-a)",
    "ndvi_b7": "NDVI-B7 (Vegetation Vigor)",
    "ndwi": "NDWI (Water Mask)",
    "turbidity_ratio": "Turbidity",
    "red_edge_slope": "Red Edge Slope (Pigment Trend)",
}

_DIRECTION_ARROWS: Dict[str, str] = {
    "up": "↑",
    "down": "↓",
    "stable": "→",
    "uncertain": "?",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_indices_from_row(row: dict) -> Dict[str, Optional[float]]:
    """Compute indices on-the-fly from band means in a lake_features row."""
    return compute_ecological_indices(
        b2_mean=row.get("b2_mean"),
        b3_mean=row.get("b3_mean"),
        b4_mean=row.get("b4_mean"),
        b5_mean=row.get("b5_mean"),
        b6_mean=row.get("b6_mean"),
        b7_mean=row.get("b7_mean"),
    )


def _classify(score: float, num_twins: int) -> str:
    """Classify a weighted score into a direction label."""
    if num_twins < _MIN_TWINS_FOR_DIRECTION:
        return "uncertain"
    if score > _DIRECTION_THRESHOLD:
        return "up"
    if score < -_DIRECTION_THRESHOLD:
        return "down"
    return "stable"


async def _fetch_band_rows(
    session: AsyncSession,
    lake_id: int,
    start_year: int,
) -> List[Dict]:
    """Fetch band mean rows from lake_features, sorted by year."""
    result = await session.execute(
        text("""
            SELECT year,
                   b2_mean, b3_mean, b4_mean, b5_mean, b6_mean, b7_mean
            FROM lake_features
            WHERE lake_id = :lake_id
              AND year >= :start_year
              AND status = 'completed'
              AND b2_mean IS NOT NULL
            ORDER BY year ASC
        """),
        {"lake_id": lake_id, "start_year": start_year},
    )
    rows = []
    for r in result.mappings().all():
        rows.append({
            "year": int(r["year"]),
            "b2_mean": float(r["b2_mean"]) if r["b2_mean"] is not None else None,
            "b3_mean": float(r["b3_mean"]) if r["b3_mean"] is not None else None,
            "b4_mean": float(r["b4_mean"]) if r["b4_mean"] is not None else None,
            "b5_mean": float(r["b5_mean"]) if r["b5_mean"] is not None else None,
            "b6_mean": float(r["b6_mean"]) if r["b6_mean"] is not None else None,
            "b7_mean": float(r["b7_mean"]) if r["b7_mean"] is not None else None,
        })
    return rows


async def _fetch_latest_band_row(
    session: AsyncSession,
    lake_id: int,
) -> Optional[Dict]:
    """Return the most recent completed lake_features row with band means."""
    result = await session.execute(
        text("""
            SELECT year,
                   b2_mean, b3_mean, b4_mean, b5_mean, b6_mean, b7_mean
            FROM lake_features
            WHERE lake_id = :lake_id
              AND status = 'completed'
              AND b2_mean IS NOT NULL
            ORDER BY year DESC
            LIMIT 1
        """),
        {"lake_id": lake_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return {
        "year": int(row["year"]),
        "b2_mean": float(row["b2_mean"]) if row["b2_mean"] is not None else None,
        "b3_mean": float(row["b3_mean"]) if row["b3_mean"] is not None else None,
        "b4_mean": float(row["b4_mean"]) if row["b4_mean"] is not None else None,
        "b5_mean": float(row["b5_mean"]) if row["b5_mean"] is not None else None,
        "b6_mean": float(row["b6_mean"]) if row["b6_mean"] is not None else None,
        "b7_mean": float(row["b7_mean"]) if row["b7_mean"] is not None else None,
    }


# ── Service ───────────────────────────────────────────────────────────────────


class EcologicalForecastService:
    """Per-year directional ecological forecast using ranked twin lakes.

    Pipeline
    --------
    1. Fetch target lake's latest band means → compute anchor indices.
    2. Run embedding similarity search to find top-k twin lakes.
    3. Assign fixed rank weights (0.28, 0.24, 0.20, 0.16, 0.12).
    4. For each twin, compute indices at matched_year and at each
       future offset (matched_year + 1, +2, +3).  Delta = future − base.
    5. For each index × each forecast year: sum (rank_weight × delta)
       across twins that have data.  Classify as up/down/stable/uncertain.
    6. Build 3-year forecast table + full audit report.
    """

    def __init__(
        self,
        session: AsyncSession,
        region_repo: RegionRepository,
        embedding_repo: EmbeddingRepository,
    ) -> None:
        self._session = session
        self._region_repo = region_repo
        self._embedding_repo = embedding_repo
        self._similarity_svc: Optional[SimilarityService] = None

    def _get_similarity_service(self) -> SimilarityService:
        if self._similarity_svc is None:
            self._similarity_svc = SimilarityService(
                embedding_repo=self._embedding_repo,
                region_repo=self._region_repo,
            )
        return self._similarity_svc

    async def generate_ecological_forecast(
        self,
        region_id: UUID,
        year: Optional[int] = None,
        num_analogs: int = 5,
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> EcologicalForecastResponse:
        # ── 1. Resolve lake ──────────────────────────────────────────────
        region = await self._region_repo.get_by_id(region_id)
        if region is None:
            raise ValueError(f"Region {region_id} not found")
        lake_id: int = region.lake_id

        # ── 2. Target lake anchor indices ────────────────────────────────
        latest_row = await _fetch_latest_band_row(self._session, lake_id)
        if latest_row is None:
            raise ValueError(
                f"No band statistics in lake_features for lake {lake_id}. "
                "Run the feature generation pipeline first."
            )
        anchor_year: int = latest_row["year"]
        anchor_indices = _compute_indices_from_row(latest_row)

        forecast_years = [anchor_year + h for h in range(1, _FORECAST_HORIZON + 1)]

        # ── 3. Similarity search ─────────────────────────────────────────
        sim_svc = self._get_similarity_service()
        search_response = await sim_svc.search_analogs(
            region_id=region_id,
            year=year,
            top_k=min(num_analogs * 4, 50),
            exclude_same_region=True,
            method=method,
        )

        if not search_response.analogs:
            return self._empty_forecast(
                region_id, lake_id, anchor_year, anchor_indices, forecast_years,
                "No analog lakes found by embedding similarity search.",
            )

        # ── 4. Build twin data ───────────────────────────────────────────
        # twin_data: list of dicts with rank, weight, matched_year, and
        #   per-index per-offset deltas.
        #
        # Structure per twin:
        #   "deltas": { idx_key: { offset: delta_value } }
        #   "index_values": { idx_key: { year_str: value } }

        twin_data: List[dict] = []

        for analog in search_response.analogs:
            if len(twin_data) >= num_analogs:
                break

            # Resolve twin lake_id
            twin_row = await self._region_repo.get_by_id_with_lake(analog.region_id)
            if twin_row is None:
                continue
            twin_lake_id: int = int(twin_row["lake_id"])
            if twin_lake_id == lake_id:
                continue

            twin_matched_year: int = analog.year

            # Fetch twin's band time-series from matched year
            band_rows = await _fetch_band_rows(
                self._session, twin_lake_id, twin_matched_year
            )
            if not band_rows:
                continue

            # Compute indices for each year
            yearly_indices: Dict[int, Dict[str, Optional[float]]] = {}
            for br in band_rows:
                yearly_indices[br["year"]] = _compute_indices_from_row(br)

            # We need the base year (matched_year) value
            base_indices = yearly_indices.get(twin_matched_year)
            if base_indices is None:
                continue

            # Compute deltas: for each future offset h = 1..3,
            #   delta = index_value(matched_year + h) - index_value(matched_year)
            deltas: Dict[str, Dict[int, float]] = {k: {} for k in _INDEX_KEYS}
            future_years_list: List[int] = []

            for h in range(1, _FORECAST_HORIZON + 1):
                future_yr = twin_matched_year + h
                future_indices = yearly_indices.get(future_yr)
                if future_indices is None:
                    continue
                future_years_list.append(future_yr)
                for idx_key in _INDEX_KEYS:
                    base_val = base_indices.get(idx_key)
                    future_val = future_indices.get(idx_key)
                    if base_val is not None and future_val is not None:
                        deltas[idx_key][h] = future_val - base_val

            # Must have at least 1 future offset with data
            if not any(deltas[k] for k in _INDEX_KEYS):
                continue

            rank = len(twin_data) + 1
            weight = _RANK_WEIGHTS.get(rank, 0.0)

            # Build index_values for audit: { idx_key: { "year": value } }
            idx_vals_for_audit: Dict[str, Dict[str, float]] = {}
            for idx_key in _INDEX_KEYS:
                idx_vals_for_audit[idx_key] = {}
                for yr, indices in yearly_indices.items():
                    val = indices.get(idx_key)
                    if val is not None:
                        idx_vals_for_audit[idx_key][str(yr)] = round(val, 6)

            twin_data.append({
                "lake_id": twin_lake_id,
                "region_id": analog.region_id,
                "rank": rank,
                "fixed_weight": weight,
                "matched_year": twin_matched_year,
                "similarity_score": analog.similarity_score,
                "future_window": future_years_list,
                "deltas": deltas,
                "index_values": idx_vals_for_audit,
            })

        if not twin_data:
            return self._empty_forecast(
                region_id, lake_id, anchor_year, anchor_indices, forecast_years,
                "No twin lakes had sufficient band data for trend extraction.",
            )

        # ── 5. Per-year weighted score + classification ──────────────────
        index_forecasts: List[IndexForecast] = []
        per_year_report: List[str] = []

        for idx_key in _INDEX_KEYS:
            current_val = anchor_indices.get(idx_key)
            yearly_dirs: List[YearlyDirection] = []

            for h in range(1, _FORECAST_HORIZON + 1):
                forecast_yr = anchor_year + h

                # Twins with usable data for this specific offset. A twin's
                # fixed rank weight only reflects its relative influence when
                # ALL twins contribute; if some are missing this year, their
                # weight must not simply vanish from the sum — that would
                # shrink the score toward "stable" purely from missing data,
                # not from an actual weaker ecological signal. So weights are
                # renormalized over only the twins that have data this year,
                # keeping the score a true weighted average (denominator 1.0)
                # regardless of how many twins dropped out.
                available: List[Tuple[dict, float]] = [
                    (twin, twin["deltas"][idx_key][h])
                    for twin in twin_data
                    if twin["deltas"].get(idx_key, {}).get(h) is not None
                ]
                twins_contributing = len(available)
                total_fixed_weight = sum(twin["fixed_weight"] for twin, _ in available)

                weighted_score = 0.0
                contributions_detail: List[str] = []
                twin_deltas: List[TwinDeltaContribution] = []

                for twin, delta in available:
                    fixed_w = twin["fixed_weight"]
                    normalized_w = (
                        fixed_w / total_fixed_weight if total_fixed_weight > 0 else 0.0
                    )
                    weighted_contribution = normalized_w * delta
                    weighted_score += weighted_contribution
                    contributions_detail.append(
                        f"Twin#{twin['rank']}(Δ={delta:+.4f}, "
                        f"w={normalized_w:.2f} [fixed {fixed_w:.2f}])"
                    )
                    twin_deltas.append(
                        TwinDeltaContribution(
                            lake_id=twin["lake_id"],
                            rank=twin["rank"],
                            matched_year=twin["matched_year"],
                            delta=round(delta, 6),
                            fixed_weight=fixed_w,
                            normalized_weight=round(normalized_w, 6),
                            weighted_contribution=round(weighted_contribution, 6),
                        )
                    )

                direction = _classify(weighted_score, twins_contributing)
                expected_value = (
                    round(current_val + weighted_score, 6)
                    if current_val is not None
                    else None
                )
                yearly_dirs.append(
                    YearlyDirection(
                        year=forecast_yr,
                        direction=direction,
                        weighted_score=round(weighted_score, 6),
                        twins_contributing=twins_contributing,
                        expected_value=expected_value,
                        twin_deltas=twin_deltas,
                    )
                )

                arrow = _DIRECTION_ARROWS[direction]
                per_year_report.append(
                    f"{_INDEX_LABELS[idx_key]} @ {forecast_yr}: "
                    f"{arrow} ({direction}) — "
                    f"weighted score = {weighted_score:+.6f}, "
                    f"{twins_contributing} twin(s) contributing"
                    + (f" [{', '.join(contributions_detail)}]" if contributions_detail else "")
                    + "."
                )

            index_forecasts.append(
                IndexForecast(
                    index_name=idx_key,
                    current_value=round(current_val, 6) if current_val is not None else 0.0,
                    yearly_directions=yearly_dirs,
                )
            )

        # ── 6. Build twin contribution list ──────────────────────────────
        twins_used: List[TwinContribution] = []
        twin_report_parts: List[str] = []

        for twin in twin_data:
            twins_used.append(
                TwinContribution(
                    lake_id=twin["lake_id"],
                    region_id=twin["region_id"],
                    rank=twin["rank"],
                    fixed_weight=twin["fixed_weight"],
                    matched_year=twin["matched_year"],
                    similarity_score=round(twin["similarity_score"], 4),
                    embedding_distance=round(1.0 - twin["similarity_score"], 4),
                    future_window=twin["future_window"],
                    index_values=twin["index_values"],
                )
            )
            twin_report_parts.append(
                f"Rank #{twin['rank']}: Lake {twin['lake_id']} "
                f"(matched year {twin['matched_year']}, "
                f"similarity {twin['similarity_score']:.4f}, "
                f"weight {twin['fixed_weight']:.2f}, "
                f"future data at offsets: "
                f"{[h for h in range(1, _FORECAST_HORIZON+1) if any(twin['deltas'][k].get(h) is not None for k in _INDEX_KEYS)]})."
            )

        # ── 7. Build table summary for explanation ───────────────────────
        table_lines = [
            f"{'Index':<20} " + " ".join(f"{yr:>6}" for yr in forecast_years)
        ]
        for ifc in index_forecasts:
            arrows = []
            for yd in ifc.yearly_directions:
                arrows.append(f"{_DIRECTION_ARROWS[yd.direction]:>6}")
            table_lines.append(f"{ifc.index_name:<20} " + " ".join(arrows))
        table_str = "\n".join(table_lines)

        # Weight scheme description
        weight_desc = ", ".join(
            f"Rank{r}={w:.2f}" for r, w in sorted(_RANK_WEIGHTS.items())
        )

        # ── 8. Audit report ──────────────────────────────────────────────
        audit_report = ForecastAuditReport(
            summary=(
                f"Ecological forecast for lake {lake_id} "
                f"(anchor year {anchor_year}) using {len(twin_data)} twin(s) "
                f"found via {method.value} embedding similarity."
            ),
            anchor_details=(
                f"Target lake {lake_id}: latest band data year {anchor_year}. "
                f"Anchor indices — "
                + ", ".join(
                    f"{_INDEX_LABELS[k]}: {anchor_indices[k]:.4f}"
                    if anchor_indices.get(k) is not None
                    else f"{_INDEX_LABELS[k]}: N/A"
                    for k in _INDEX_KEYS
                )
                + "."
            ),
            weight_scheme=(
                f"Fixed rank-based weights: {weight_desc}. "
                f"If a twin has no data for a forecast year, its weight is 0 "
                f"for that year (excluded, not redistributed)."
            ),
            classification_rule=(
                f"Score > +{_DIRECTION_THRESHOLD} → Upward (↑). "
                f"Score < −{_DIRECTION_THRESHOLD} → Downward (↓). "
                f"Score within ±{_DIRECTION_THRESHOLD} → Stable (→). "
                f"Fewer than {_MIN_TWINS_FOR_DIRECTION} twins → Uncertain (?)."
            ),
            twin_details=twin_report_parts,
            per_year_reasoning=per_year_report,
        )

        explanation = (
            f"{audit_report.summary}\n\n"
            f"Forecast table:\n{table_str}"
        )

        logger.info(
            "Ecological forecast generated",
            region_id=str(region_id),
            lake_id=lake_id,
            anchor_year=anchor_year,
            num_twins=len(twin_data),
        )

        return EcologicalForecastResponse(
            region_id=region_id,
            lake_id=lake_id,
            current_year=anchor_year,
            forecast_years=forecast_years,
            index_forecasts=index_forecasts,
            twins_used=twins_used,
            audit_report=audit_report,
            explanation=explanation,
        )

    # ── Fallback ──────────────────────────────────────────────────────────

    @staticmethod
    def _empty_forecast(
        region_id: UUID,
        lake_id: int,
        current_year: int,
        anchor_indices: Dict[str, Optional[float]],
        forecast_years: List[int],
        reason: str,
    ) -> EcologicalForecastResponse:
        """Build a forecast with all years marked uncertain."""
        index_forecasts = []
        for idx_key in _INDEX_KEYS:
            val = anchor_indices.get(idx_key, 0.0)
            yearly_dirs = [
                YearlyDirection(
                    year=yr,
                    direction="uncertain",
                    weighted_score=0.0,
                    twins_contributing=0,
                    expected_value=val if val is not None else None,
                    twin_deltas=[],
                )
                for yr in forecast_years
            ]
            index_forecasts.append(
                IndexForecast(
                    index_name=idx_key,
                    current_value=val if val is not None else 0.0,
                    yearly_directions=yearly_dirs,
                )
            )
        return EcologicalForecastResponse(
            region_id=region_id,
            lake_id=lake_id,
            current_year=current_year,
            forecast_years=forecast_years,
            index_forecasts=index_forecasts,
            twins_used=[],
            audit_report=ForecastAuditReport(
                summary=reason,
                anchor_details="",
                weight_scheme="",
                classification_rule="",
                twin_details=[],
                per_year_reasoning=[],
            ),
            explanation=reason,
        )
