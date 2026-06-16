from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnalogResult(BaseModel):
    region_id: UUID
    center_lat: float
    center_lon: float
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    year: int
    dominant_ecosystem: Optional[str] = None


class SimilaritySearchResponse(BaseModel):
    query_region_id: UUID
    query_year: int
    analogs: List[AnalogResult]
    search_latency_ms: float
