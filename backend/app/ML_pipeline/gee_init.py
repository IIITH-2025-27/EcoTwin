"""
Google Earth Engine initialization for backend processing.

Call ``ensure_gee_initialized()`` before any ``ee.*`` API usage.

Authentication modes
--------------------
1. Service Account
   USE_GEE_SERVICE_ACCOUNT=True

2. Personal Google Account
   USE_GEE_SERVICE_ACCOUNT=False
   (Requires: earthengine authenticate)
"""

from __future__ import annotations

import os

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_initialized = False


def ensure_gee_initialized() -> None:
    """
    Initialize the Earth Engine client exactly once.

    Authentication mode is controlled by:

        USE_GEE_SERVICE_ACCOUNT=True   -> Service Account
        USE_GEE_SERVICE_ACCOUNT=False  -> Personal Google Account
    """

    global _initialized

    if _initialized:
        return

    import ee  # noqa: PLC0415

    # ------------------------------------------------------------------
    # Service Account Authentication
    # ------------------------------------------------------------------
    if settings.USE_GEE_SERVICE_ACCOUNT:

        key_path = (settings.GEE_SERVICE_ACCOUNT_KEY_PATH or "").strip()
        email = (settings.GEE_SERVICE_ACCOUNT_EMAIL or "").strip()

        if not key_path:
            raise RuntimeError(
                "USE_GEE_SERVICE_ACCOUNT=True "
                "but GEE_SERVICE_ACCOUNT_KEY_PATH is not configured."
            )

        if not email:
            raise RuntimeError(
                "USE_GEE_SERVICE_ACCOUNT=True "
                "but GEE_SERVICE_ACCOUNT_EMAIL is not configured."
            )

        if not os.path.isfile(key_path):
            raise FileNotFoundError(
                f"Service account key not found: {key_path}"
            )

        credentials = ee.ServiceAccountCredentials(
            email,
            key_path,
        )

        ee.Initialize(credentials)

        logger.info(
            "Earth Engine initialized using Service Account",
            email=email,
        )

    # ------------------------------------------------------------------
    # Personal Google Account Authentication
    # ------------------------------------------------------------------
    else:

        try:
            ee.Initialize()

            logger.info(
                "Earth Engine initialized using Personal Google Account."
            )

        except Exception as exc:

            raise RuntimeError(
                "\n"
                "No authenticated Google Earth Engine user found.\n\n"
                "Run the following command once:\n\n"
                "    earthengine authenticate\n\n"
                "Then restart the backend."
            ) from exc

    _initialized = True