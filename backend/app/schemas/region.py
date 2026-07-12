from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RegionResponse(BaseModel):
    region_id: UUID
    hydrolake_id: str
    name: str
    country: str
    center_lat: float
    center_lon: float
    area_sqkm: float
    bbox: Optional[dict[str, float]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegionMapResponse(BaseModel):
    region_id: UUID
    hydrolake_id: str
    name: str
    country: str
    center_lat: float
    center_lon: float
    area_sqkm: float
    bbox: Optional[dict[str, float]] = None
    geometry: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class RegionFeatureResponse(BaseModel):
    region_id: UUID
    year: int
    ndvi_mean: Optional[float] = None
    ndvi_std: Optional[float] = None
    ndwi_mean: Optional[float] = None
    ndwi_std: Optional[float] = None
    nbr_mean: Optional[float] = None
    nbr_std: Optional[float] = None
    dominant_ecosystem: Optional[str] = None

    model_config = {"from_attributes": True}


class RegionQueryRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude")


class RegionQueryResponse(BaseModel):
    region_id: UUID
    center_lat: float
    center_lon: float
    distance_km: float


class RegionSummaryResponse(BaseModel):
    region: RegionResponse
    latest_features: Optional[RegionFeatureResponse] = None
