"""Repository for lake_features table operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lake_feature import LakeFeature
from app.models.lake_image import LakeImage
from app.repositories.base_repository import BaseRepository


class LakeFeatureRepository(BaseRepository[LakeFeature]):
    """Async repository for lake feature CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(LakeFeature, session)

    async def get_by_lake_year(
        self, lake_id: int, year: int
    ) -> Optional[LakeFeature]:
        """Return the feature row for a given lake + year, or None."""
        result = await self.session.execute(
            select(LakeFeature).where(
                LakeFeature.lake_id == lake_id,
                LakeFeature.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def exists(self, lake_id: int, year: int) -> bool:
        """Check whether a completed feature row already exists."""
        row = await self.get_by_lake_year(lake_id, year)
        return row is not None and row.status == "completed"

    async def get_merged_images(
        self, year: Optional[int] = None
    ) -> List[LakeImage]:
        """Return all lake_images rows with status='merged', optionally filtered by year."""
        stmt = select(LakeImage).where(LakeImage.status == "merged")
        if year is not None:
            stmt = stmt.where(LakeImage.year == year)
        stmt = stmt.order_by(LakeImage.lake_id, LakeImage.year)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        lake_id: int,
        year: int,
        features: Dict[str, Any],
        overwrite: bool = False,
    ) -> LakeFeature:
        """Insert or update a lake_features row.

        When overwrite=True, existing rows are updated.
        Otherwise only new rows are inserted.
        """
        now = datetime.now(timezone.utc)
        values = {
            "lake_id": lake_id,
            "year": year,
            "updated_at": now,
            **features,
        }

        if overwrite:
            # Use PostgreSQL ON CONFLICT … DO UPDATE
            stmt = pg_insert(LakeFeature).values(**values)
            update_cols = {
                k: v
                for k, v in values.items()
                if k not in ("lake_id", "year")
            }
            stmt = stmt.on_conflict_do_update(
                constraint="uq_lake_features_lake_year",
                set_=update_cols,
            )
            await self.session.execute(stmt)
            await self.session.flush()
            return await self.get_by_lake_year(lake_id, year)  # type: ignore[return-value]
        else:
            # Simple insert — caller should have checked existence first
            feature = LakeFeature(created_at=now, **values)
            return await self.save(feature)

    async def mark_failed(
        self, lake_id: int, year: int, error_message: str
    ) -> None:
        """Create or update a row with status='failed' and the error message."""
        existing = await self.get_by_lake_year(lake_id, year)
        if existing:
            existing.status = "failed"
            existing.error_message = error_message
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
        else:
            feature = LakeFeature(
                lake_id=lake_id,
                year=year,
                status="failed",
                error_message=error_message,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            await self.save(feature)
