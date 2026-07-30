from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.region import Region
from app.models.lake import Lake
from app.repositories.base_repository import BaseRepository


class RegionRepository(BaseRepository[Region]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Region, session)

    async def get_by_id(self, region_id: UUID) -> Optional[Region]:
        result = await self.session.execute(
            select(Region).where(Region.region_id == region_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_lake(self, region_id: UUID) -> Optional[dict]:
        """Return region joined with lake metadata as a dict."""
        result = await self.session.execute(
            text("""
                SELECT r.region_id, r.lake_id, r.year, r.center_lat, r.center_lon,
                       r.status, r.error_message, r.created_at, r.updated_at,
                       l.display_name AS name,
                       l.country,
                       l.state,
                       l.area_sqkm,
                       l.lake_name AS hydrolake_id
                FROM regions r
                JOIN lakes l ON l.lake_id = r.lake_id
                WHERE r.region_id = :region_id
            """),
            {"region_id": str(region_id)},
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    async def find_nearest(self, lat: float, lon: float) -> Optional[Region]:
        """Return the region whose center is geometrically nearest to (lat, lon)."""
        result = await self.session.execute(
            select(Region)
            .order_by(
                func.pow(Region.center_lat - lat, 2)
                + func.pow(Region.center_lon - lon, 2)
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_country(self, country: str) -> list[dict]:
        """
        Return all lake-regions for a country, joining lakes for display metadata.
        Returns the latest year row per lake so the map only shows one polygon per lake.
        """
        result = await self.session.execute(
            text("""
                SELECT DISTINCT ON (r.lake_id)
                    r.region_id,
                    r.lake_id,
                    r.year,
                    r.center_lat,
                    r.center_lon,
                    r.created_at,
                    r.updated_at,
                    l.display_name AS name,
                    l.country,
                    l.state,
                    l.area_sqkm,
                    l.lake_name AS hydrolake_id
                FROM regions r
                JOIN lakes l ON l.lake_id = r.lake_id
                WHERE lower(l.country) = lower(:country)
                  AND r.embedding IS NOT NULL
                ORDER BY r.lake_id, r.year DESC
            """),
            {"country": country},
        )
        return [dict(row) for row in result.mappings().all()]

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Region.region_id)))
        return result.scalar_one()
