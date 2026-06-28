"""
Google Earth Engine initialization for Celery workers.

Call ``ensure_gee_initialized()`` before any ``ee.*`` API usage.  Uses a
service-account JSON key when configured, otherwise falls back to user
credentials from ``earthengine authenticate``.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

_initialized = False


def ensure_gee_initialized() -> None:
    """Initialize the Earth Engine client once per worker process."""
    global _initialized
    if _initialized:
        return

    import ee  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    key_path = (settings.GEE_SERVICE_ACCOUNT_KEY_PATH or "").strip()
    email = (settings.GEE_SERVICE_ACCOUNT_EMAIL or "").strip()

    if key_path and email:
        if not os.path.isfile(key_path):
            raise RuntimeError(
                f"GEE service-account key not found at {key_path!r}. "
                "Mount the key into the container or update GEE_SERVICE_ACCOUNT_KEY_PATH."
            )
        credentials = ee.ServiceAccountCredentials(email, key_path)
        ee.Initialize(credentials)
        logger.info("Earth Engine initialized with service account", email=email)
    else:
        ee.Initialize()
        logger.info("Earth Engine initialized with default credentials")

    _initialized = True
