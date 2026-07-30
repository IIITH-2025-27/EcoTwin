"""
FeatureRepository — stubbed out since region_features table does not exist in the
current database schema. Kept here to avoid import errors in any code that
references it. All methods return None / empty list.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class FeatureRepository:
    """No-op repository — region_features table not yet migrated."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_region_year(self, region_id: UUID, year: int) -> None:
        return None

    async def get_all_years(self, region_id: UUID) -> List:
        return []
