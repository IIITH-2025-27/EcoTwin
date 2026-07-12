from typing import Any, Optional

from pydantic import BaseModel


class LakeSearchResponse(BaseModel):
    lake_id: int
    display_name: str
    state: Optional[str] = None
    area_sqkm: Optional[float] = None


class LakeCountResponse(BaseModel):
    country: str
    total_lakes: int


class LakeGeometryResponse(LakeSearchResponse):
    country: str
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    geometry: Optional[dict[str, Any]] = None


class LakeMarkerResponse(BaseModel):
    """Lightweight response for map marker rendering — no geometry payload."""
    lake_id: int
    display_name: str
    state: Optional[str] = None
    area_sqkm: Optional[float] = None
    center_lat: float
    center_lon: float
