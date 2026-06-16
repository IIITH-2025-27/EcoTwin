from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.temporal_profile import TemporalProfile
from app.repositories.base_repository import BaseRepository


class TemporalRepository(BaseRepository[TemporalProfile]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TemporalProfile, session)

    async def get_profile(self, region_id: UUID) -> List[TemporalProfile]:
        result = await self.session.execute(
            select(TemporalProfile)
            .where(TemporalProfile.region_id == region_id)
            .order_by(TemporalProfile.year.asc())
        )
        return list(result.scalars().all())
