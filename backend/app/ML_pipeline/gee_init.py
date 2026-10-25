"""
Google Earth Engine initialization for backend processing.

Call ``ensure_gee_initialized()`` before any ``ee.*`` API usage.

Authentication modes
--------------------
1. Service Account
   USE_GEE_SERVICE_ACCOUNT=True

   Several service accounts can be used one after another: the configured
   key (GEE_SERVICE_ACCOUNT_KEY_PATH) first, then the keys listed in
   GEE_SERVICE_ACCOUNT_KEY_PATHS (comma-separated) or, if that is empty,
   every ``gee_key*.json`` next to the configured key. When Earth Engine
   rejects the active account (quota / rate limit / invalid key), callers
   switch with ``rotate_gee_account()``.

2. Personal Google Account
   USE_GEE_SERVICE_ACCOUNT=False
   (Requires: earthengine authenticate)
"""

from __future__ import annotations

import glob
import json
import os
import threading
from typing import List, Optional, Tuple

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_initialized = False

# Service-account rotation state
_accounts: List[Tuple[str, str]] = []   # (key_path, email)
_active: int = 0
_exhausted: set = set()                 # accounts that failed this process


def _key_email(key_path: str) -> str:
    """The service account's email, read from its key file."""
    with open(key_path) as fh:
        return json.load(fh)["client_email"]


def _discover_accounts() -> List[Tuple[str, str]]:
    key_path = (settings.GEE_SERVICE_ACCOUNT_KEY_PATH or "").strip()
    if not key_path:
        raise RuntimeError(
            "USE_GEE_SERVICE_ACCOUNT=True "
            "but GEE_SERVICE_ACCOUNT_KEY_PATH is not configured."
        )
    if not os.path.isfile(key_path):
        raise FileNotFoundError(f"Service account key not found: {key_path}")

    extra = [p.strip() for p in (settings.GEE_SERVICE_ACCOUNT_KEY_PATHS or "").split(",") if p.strip()]
    if not extra:
        extra = sorted(glob.glob(os.path.join(os.path.dirname(key_path) or ".", "gee_key*.json")))

    paths: List[str] = []
    for p in [key_path, *extra]:
        if os.path.isfile(p) and os.path.abspath(p) not in {os.path.abspath(q) for q in paths}:
            paths.append(p)

    accounts = []
    for p in paths:
        try:
            email = _key_email(p)
        except Exception as exc:  # unreadable / not a service-account key
            logger.warning("Skipping GEE key file", key=os.path.basename(p), error=str(exc)[:100])
            continue
        accounts.append((p, email))
    if not accounts:
        raise RuntimeError("No usable GEE service-account key found.")
    # The configured email wins for the configured key
    configured_email = (settings.GEE_SERVICE_ACCOUNT_EMAIL or "").strip()
    if configured_email and os.path.abspath(accounts[0][0]) == os.path.abspath(key_path):
        accounts[0] = (accounts[0][0], configured_email)
    return accounts


def _initialize_account(index: int) -> None:
    import ee  # noqa: PLC0415

    key_path, email = _accounts[index]
    ee.Initialize(ee.ServiceAccountCredentials(email, key_path))
    logger.info(
        "Earth Engine initialized using Service Account",
        email=email,
        account=f"{index + 1}/{len(_accounts)}",
    )


def ensure_gee_initialized() -> None:
    """
    Initialize the Earth Engine client exactly once.

    Authentication mode is controlled by:

        USE_GEE_SERVICE_ACCOUNT=True   -> Service Account(s)
        USE_GEE_SERVICE_ACCOUNT=False  -> Personal Google Account
    """
    global _initialized, _accounts, _active

    with _lock:
        if _initialized:
            return

        import ee  # noqa: PLC0415

        # ------------------------------------------------------------------
        # Service Account Authentication
        # ------------------------------------------------------------------
        if settings.USE_GEE_SERVICE_ACCOUNT:
            _accounts = _discover_accounts()
            last_error: Optional[Exception] = None
            for index in range(len(_accounts)):
                try:
                    _initialize_account(index)
                    _active = index
                    break
                except Exception as exc:
                    last_error = exc
                    _exhausted.add(index)
                    logger.warning(
                        "GEE account failed to initialize",
                        email=_accounts[index][1],
                        error=str(exc)[:200],
                    )
            else:
                raise RuntimeError(f"No GEE service account could be initialized: {last_error}")
            logger.info("GEE service accounts available", count=len(_accounts))

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


def current_gee_account() -> int:
    """Index of the active service account (0 in personal-account mode)."""
    return _active


def gee_account_count() -> int:
    return len(_accounts)


def rotate_gee_account(failed_index: int, reason: str) -> bool:
    """Switch to the next usable service account after ``failed_index``
    was rejected (quota / rate limit / invalid key).

    Returns True if a request should be retried — either another thread
    already switched away from ``failed_index``, or a new account is now
    active — and False when no other account is left.
    """
    global _active

    with _lock:
        if not _accounts:
            return False
        if _active != failed_index:
            return True  # another thread already switched
        _exhausted.add(failed_index)
        for step in range(1, len(_accounts)):
            candidate = (failed_index + step) % len(_accounts)
            if candidate in _exhausted:
                continue
            try:
                _initialize_account(candidate)
            except Exception as exc:
                _exhausted.add(candidate)
                logger.warning(
                    "GEE account failed to initialize",
                    email=_accounts[candidate][1],
                    error=str(exc)[:200],
                )
                continue
            _active = candidate
            logger.warning(
                "Switched GEE service account",
                from_email=_accounts[failed_index][1],
                to_email=_accounts[candidate][1],
                reason=reason[:200],
            )
            return True
        logger.error("All GEE service accounts are exhausted", reason=reason[:200])
        return False
