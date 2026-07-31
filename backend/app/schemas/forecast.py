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
