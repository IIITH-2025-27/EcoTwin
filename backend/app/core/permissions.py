"""Pipeline permission dependency for FastAPI endpoints.

Usage in a route:

    @router.post("/some-pipeline-action")
    async def some_action(
        _perm: None = Depends(require_pipeline_permission("sync_lakes")),
    ):
        ...  # existing code unchanged
"""

from __future__ import annotations

from typing import Dict

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.pipeline_permission import PipelinePermission

logger = structlog.get_logger(__name__)

_MASTER_KEY = "allow_data_pipeline_run"
_DENIED_DETAIL = "Data Pipeline run Access denied"


def require_pipeline_permission(permission_key: str):
    """Return a FastAPI dependency that enforces the master + individual permission."""

    async def _check(db: AsyncSession = Depends(get_db)) -> None:
        rows = (
            await db.execute(
                select(PipelinePermission.permission_key, PipelinePermission.is_enabled)
                .where(
                    PipelinePermission.permission_key.in_(
                        [_MASTER_KEY, permission_key]
                    )
                )
            )
        ).all()

        perm_map = {key: enabled for key, enabled in rows}

        master_enabled = perm_map.get(_MASTER_KEY, False)
        individual_enabled = perm_map.get(permission_key, False)

        if not master_enabled or not individual_enabled:
            logger.warning(
                "Pipeline permission denied",
                permission_key=permission_key,
                master_enabled=master_enabled,
                individual_enabled=individual_enabled,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_DENIED_DETAIL,
            )

    return _check


async def load_pipeline_permissions(db: AsyncSession) -> Dict[str, bool]:
    """Load all pipeline permissions as a flat dict.

    Returns a dictionary like:
        {
            "allow_data_pipeline_run": False,
            "sync_lakes": False,
            ...
        }
    """
    rows = (
        await db.execute(
            select(PipelinePermission.permission_key, PipelinePermission.is_enabled)
        )
    ).all()
    return {key: enabled for key, enabled in rows}
