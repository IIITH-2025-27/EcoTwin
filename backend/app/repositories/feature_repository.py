from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.region import RegionFeature
from app.repositories.base_repository import BaseRepository


class FeatureRepository(BaseRepository[RegionFeature]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RegionFeature, session)

    async def get_by_region_year(
        self, region_id: UUID, year: int
    ) -> Optional[RegionFeature]:
        result = await self.session.execute(
            select(RegionFeature).where(
                RegionFeature.region_id == region_id,
                RegionFeature.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_years(self, region_id: UUID) -> List[RegionFeature]:
        result = await self.session.execute(
            select(RegionFeature)
            .where(RegionFeature.region_id == region_id)
            .order_by(RegionFeature.year.asc())
        )
        return list(result.scalars().all())
