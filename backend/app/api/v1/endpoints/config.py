"""
GET /config  — return frontend-safe application configuration.

Only exposes pipeline permission flags.  No secrets, credentials,
or internal environment variables are included.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import DatabaseDep
from app.core.permissions import load_pipeline_permissions

router = APIRouter(tags=["Config"])


@router.get("")
async def get_config(db: DatabaseDep) -> dict:
    """Return the public application configuration for the frontend."""
    perms = await load_pipeline_permissions(db)

    master = perms.pop("allow_data_pipeline_run", False)

    return {
        "allow_data_pipeline_run": master,
        "pipeline_permissions": perms,
    }
