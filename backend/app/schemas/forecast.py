from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class YearlyIndicator(BaseModel):
    year: int
    value: float


class TemporalDataResponse(BaseModel):
    region_id: UUID
    ndvi: List[YearlyIndicator]
    ndwi: List[YearlyIndicator]
    nbr: List[YearlyIndicator]


class ForecastHorizon(BaseModel):
    year: int
    ndvi_forecast: float
    ndwi_forecast: float
    nbr_forecast: float
    confidence: float = Field(..., ge=0.0, le=1.0)


class ForecastResponse(BaseModel):
    region_id: UUID
    current_year: int
    forecast_horizons: List[ForecastHorizon]
    best_analog_id: Optional[UUID] = None
    analog_match_year: Optional[int] = None
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    vegetation_trend: str  # "increasing" | "stable" | "declining"
    water_trend: str
    burn_severity_trend: str
    explanation: str


# ── Forecasting Module I/O ───────────────────────────────────────────────────

class AnalogForecastInput(BaseModel):
    """One ranked result from the similarity search, consumed by the forecasting module."""

    lake_id: int
    region_id: UUID
    matched_window_start: int  # first year of the matched window
    matched_window_end: int    # last year of the matched window (= query year)
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    forecast_horizon: int = Field(3, ge=1, description="Number of future years to forecast")


class SelectedAnalog(BaseModel):
    """Metadata for one analog that was ultimately selected for the forecast."""

    lake_id: int
    region_id: UUID
    matched_window_start: int
    matched_window_end: int
    similarity_score: float
    weight: float = Field(..., ge=0.0, le=1.0)


class EmbeddingForecastResult(BaseModel):
    """Output of the forecasting module: one weighted-average embedding per horizon year."""

    # horizon_year → weighted-average embedding vector
    forecast_embeddings: Dict[int, List[float]]
    selected_analogs: List[SelectedAnalog]
    num_analogs_used: int
    forecast_horizon: int


# ── Ecological Index Forecast I/O ─────────────────────────────────────────────


class TwinDeltaContribution(BaseModel):
    """One twin lake's raw delta contribution to a single forecast year."""

    lake_id: int
    rank: int                          # 1-based rank by similarity
    matched_year: int                  # twin's own base year the delta is measured from
    delta: float                       # index_value(matched_year + h) - index_value(matched_year)
    fixed_weight: float                # rank-based weight (0.28, 0.24, …), before renormalization
    normalized_weight: float           # fixed_weight rescaled so this year's contributing twins sum to 1.0
    weighted_contribution: float       # normalized_weight * delta — this twin's share of weighted_score


class YearlyDirection(BaseModel):
    """Classification for one index at one forecast year."""

    year: int
    direction: str                     # "up" | "down" | "stable" | "uncertain"
    weighted_score: float              # combined weighted delta for this year
    twins_contributing: int            # how many twins had data for this year
    expected_value: Optional[float] = None   # current_value + weighted_score, or None if no anchor
    twin_deltas: List[TwinDeltaContribution] = Field(default_factory=list)


class IndexForecast(BaseModel):
    """One row of the 3-year forecast table — one index across all years."""

    index_name: str                    # "ndci", "ndvi_b7", etc.
    current_value: float               # target lake's latest actual value
    yearly_directions: List[YearlyDirection]


class TwinContribution(BaseModel):
    """One twin lake's contribution to the ecological forecast."""

    lake_id: int
    region_id: UUID
    rank: int                          # 1-based rank by similarity
    fixed_weight: float                # rank-based weight (0.40, 0.25, …)
    matched_year: int
    similarity_score: float
    embedding_distance: float
    future_window: List[int]           # years with data after match
    index_values: Dict[str, Dict[str, float]]  # index -> {year_str: value}


class ForecastAuditReport(BaseModel):
    """Detailed audit trail explaining how the forecast was derived."""

    summary: str
    anchor_details: str
    weight_scheme: str
    classification_rule: str
    twin_details: List[str]
    per_year_reasoning: List[str]


class EcologicalForecastResponse(BaseModel):
    """Per-year directional ecological forecast for one target lake."""

    region_id: UUID
    lake_id: int
    current_year: int
    forecast_years: List[int]          # e.g. [2026, 2027, 2028]
    index_forecasts: List[IndexForecast]
    twins_used: List[TwinContribution]
    audit_report: ForecastAuditReport
    explanation: str

