import math
from uuid import UUID

import structlog

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
        row = await self._repo.get_by_id_with_lake(region_id)
        if not row:
            raise RegionNotFoundException(str(region_id))

        region_resp = RegionResponse(
            region_id=row["region_id"],
            lake_id=row["lake_id"],
            year=row["year"],
            name=row.get("name"),
            hydrolake_id=row.get("hydrolake_id"),
            country=row.get("country"),
            state=row.get("state"),
            center_lat=row["center_lat"],
            center_lon=row["center_lon"],
            area_sqkm=row.get("area_sqkm"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
        return RegionSummaryResponse(region=region_resp, latest_features=None)

    async def list_regions(self, country: str = "India") -> list[RegionMapResponse]:
        rows = await self._repo.list_by_country(country)
        return [
            RegionMapResponse(
                region_id=row["region_id"],
                lake_id=row["lake_id"],
                year=row["year"],
                name=row.get("name"),
                hydrolake_id=row.get("hydrolake_id"),
                country=row.get("country"),
                state=row.get("state"),
                center_lat=row["center_lat"],
                center_lon=row["center_lon"],
                area_sqkm=row.get("area_sqkm"),
                geometry=None,
            )
            for row in rows
        ]

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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
