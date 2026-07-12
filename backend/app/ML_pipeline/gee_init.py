"""
Google Earth Engine initialization for backend processing.

Call ``ensure_gee_initialized()`` before any ``ee.*`` API usage.

Auth order:
  1. Service-account JSON key  — when GEE_SERVICE_ACCOUNT_KEY_PATH *and*
     GEE_SERVICE_ACCOUNT_EMAIL are both set **and** the key file exists.
  2. User credentials           — fallback for local development.
     Run ``earthengine authenticate`` once to store credentials.
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
    email    = (settings.GEE_SERVICE_ACCOUNT_EMAIL    or "").strip()

    if key_path and email:
        if os.path.isfile(key_path):
            credentials = ee.ServiceAccountCredentials(email, key_path)
            ee.Initialize(credentials)
            logger.info("Earth Engine initialized with service account", email=email)
        else:
            # Key file not found — common in local dev where the container path
            # does not exist.  Fall back to user credentials stored by
            # `earthengine authenticate`.
            logger.warning(
                "GEE service-account key not found — falling back to user credentials."
                " Run 'earthengine authenticate' if this is the first run.",
                key_path=key_path,
            )
            ee.Initialize()
            logger.info("Earth Engine initialized with default (user) credentials")
    else:
        ee.Initialize()
        logger.info("Earth Engine initialized with default (user) credentials")

    _initialized = True
