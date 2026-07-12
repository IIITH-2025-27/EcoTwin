import math
from uuid import UUID

import structlog
from geoalchemy2.shape import to_shape

from app.core.exceptions import RegionNotFoundException
from app.repositories.region_repository import RegionRepository
from app.schemas.region import (
    RegionFeatureResponse,
    RegionMapResponse,
    RegionQueryResponse,
    RegionResponse,
    RegionSummaryResponse,
)

logger = structlog.get_logger(__name__)

_EARTH_RADIUS_KM = 6_371.0


class RegionService:
    def __init__(self, region_repo: RegionRepository) -> None:
        self._repo = region_repo

    async def get_region_summary(self, region_id: UUID) -> RegionSummaryResponse:
        region = await self._repo.get_by_id(region_id)
        if not region:
            raise RegionNotFoundException(str(region_id))

        latest_feature = await self._repo.get_latest_features(region_id)
        feature_response = (
            RegionFeatureResponse.model_validate(latest_feature)
            if latest_feature
            else None
        )
        return RegionSummaryResponse(
            region=RegionResponse.model_validate(region),
            latest_features=feature_response,
        )

    async def list_regions(self, country: str = "India") -> list[RegionMapResponse]:
        regions = await self._repo.list_by_country(country)
        return [_map_region(region) for region in regions]

    async def find_region_by_coordinates(
        self, lat: float, lon: float
    ) -> RegionQueryResponse:
        region = await self._repo.find_nearest(lat, lon)
        if not region:
            raise RegionNotFoundException(f"lat={lat}, lon={lon}")

        distance_km = round(_haversine_km(lat, lon, region.center_lat, region.center_lon), 3)
        return RegionQueryResponse(
            region_id=region.region_id,
            center_lat=region.center_lat,
            center_lon=region.center_lon,
            distance_km=distance_km,
        )


def _map_region(region) -> RegionMapResponse:
    geometry = None
    if region.geom is not None:
        geometry = to_shape(region.geom).__geo_interface__

    return RegionMapResponse(
        region_id=region.region_id,
        hydrolake_id=region.hydrolake_id,
        name=region.name,
        country=region.country,
        center_lat=region.center_lat,
        center_lon=region.center_lon,
        area_sqkm=region.area_sqkm,
        bbox=region.bbox,
        geometry=geometry,
        created_at=region.created_at,
        updated_at=region.updated_at,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
