from app.schemas.common import ErrorResponse, HealthResponse, PaginatedResponse
from app.schemas.forecast import ForecastHorizon, ForecastResponse, TemporalDataResponse, YearlyIndicator
from app.schemas.region import (
    RegionFeatureResponse,
    RegionQueryRequest,
    RegionQueryResponse,
    RegionResponse,
    RegionSummaryResponse,
)
from app.schemas.report import ReportGenerateRequest, ReportResponse
from app.schemas.similarity import AnalogResult, SimilaritySearchResponse

__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "PaginatedResponse",
    "ForecastHorizon",
    "ForecastResponse",
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
