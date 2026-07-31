from app.schemas.common import ErrorResponse, HealthResponse, PaginatedResponse
from app.schemas.forecast import (
    AnalogForecastInput,
    EmbeddingForecastResult,
    ForecastHorizon,
    ForecastResponse,
    SelectedAnalog,
    TemporalDataResponse,
    YearlyIndicator,
)
from app.schemas.region import (
    RegionFeatureResponse,
    RegionQueryRequest,
    RegionQueryResponse,
    RegionMapResponse,
    RegionResponse,
    RegionSummaryResponse,
)
from app.schemas.report import ReportGenerateRequest, ReportResponse
from app.schemas.similarity import AnalogResult, SimilaritySearchResponse

__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "PaginatedResponse",
    "AnalogForecastInput",
    "EmbeddingForecastResult",
    "ForecastHorizon",
    "ForecastResponse",
    "SelectedAnalog",
    "TemporalDataResponse",
    "YearlyIndicator",
    "RegionFeatureResponse",
    "RegionQueryRequest",
    "RegionQueryResponse",
    "RegionResponse",
    "RegionSummaryResponse",
    "ReportGenerateRequest",
    "ReportResponse",
    "AnalogResult",
    "SimilaritySearchResponse",
]
