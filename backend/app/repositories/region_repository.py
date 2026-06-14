from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.region import Region, RegionFeature
from app.repositories.base_repository import BaseRepository


class RegionRepository(BaseRepository[Region]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Region, session)

    async def get_by_id(self, region_id: UUID) -> Optional[Region]:
        result = await self.session.execute(
            select(Region)
            .where(Region.region_id == region_id)
            .options(selectinload(Region.features))
        )
        return result.scalar_one_or_none()

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

    async def get_latest_features(self, region_id: UUID) -> Optional[RegionFeature]:
        result = await self.session.execute(
            select(RegionFeature)
            .where(RegionFeature.region_id == region_id)
            .order_by(RegionFeature.year.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Region.region_id)))
        return result.scalar_one()
