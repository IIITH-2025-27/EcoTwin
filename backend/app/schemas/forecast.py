from typing import List, Optional
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
