"""
High-level entry point for the per-lake tile-based imagery download pipeline.

Manages global progress state so the API can poll ``/imagery/status``:
lake-year counters for the progress bar plus tile counters for detail.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

import structlog

from pathlib import Path

from app.image_acquisition.config import get_image_acquisition_config
from app.image_acquisition.downloader import LakeImageDownloader
from app.image_acquisition.storage import (
    default_data_root,
    validate_data_root,
)
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = structlog.get_logger(__name__)

# ── Global progress state ─────────────────────────────────────────────────
#
# ``total`` / ``processed`` count lake-years (one per lake per year), so the
# progress bar always ends at 100 %. Tile counters are reported separately:
# the number of tiles per lake is only known once its grid is built.
#
# Status lifecycle: idle → running → (cancelling →) done | cancelled | failed

_lock = threading.Lock()

_ACTIVE_STATUSES = ("running", "cancelling")

_progress: Dict = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0,
    "tiles_completed": 0,
    "tiles_failed": 0,
    "active_lakes": 0,
    "current_lake_id": None,
    "current_year": None,
    "current_tile_index": None,
    "year_roots": {},
    "errors": [],
}

_cancelled = False


def get_imagery_progress() -> Dict:
    """Return a snapshot of the current pipeline progress."""
    with _lock:
        snapshot = dict(_progress)
        snapshot["errors"] = list(_progress["errors"])
        snapshot["year_roots"] = dict(_progress["year_roots"])
        return snapshot


def is_imagery_active() -> bool:
    """True while a download is running or still winding down after cancel."""
    with _lock:
        return _progress["status"] in _ACTIVE_STATUSES


def claim_imagery_run(year_roots: Dict[str, str]) -> bool:
    """Atomically mark a new run as started.

    Called by the API before the background task is queued, so a second
    request (or a poll right after the first one) never sees a stale
    ``done`` / ``idle`` state. ``year_roots`` maps each year of the run to
    its storage root (shown in the UI). Returns False if a run is active.
    """
    global _cancelled
    with _lock:
        if _progress["status"] in _ACTIVE_STATUSES:
            return False
        _cancelled = False
        _progress.update(
            status="running",
            total=0,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            tiles_completed=0,
            tiles_failed=0,
            active_lakes=0,
            current_lake_id=None,
            current_year=None,
            current_tile_index=None,
            year_roots=dict(year_roots),
            errors=[],
        )
        return True


def cancel_imagery_pipeline() -> bool:
    """Request cancellation of the running pipeline.

    The status becomes ``cancelling`` until in-flight tiles finish, then
    ``cancelled``.
    """
    global _cancelled
    with _lock:
        if _progress["status"] != "running":
            return False
        _cancelled = True
        _progress["status"] = "cancelling"
    logger.warning("Imagery pipeline cancellation requested")
    return True


def is_imagery_cancelled() -> bool:
    """Return True if cancellation has been requested."""
    return _cancelled


def _add_error(message: str) -> None:
    """Append an error (caller holds the lock); keep the last 100."""
    _progress["errors"].append(message)
    if len(_progress["errors"]) > 100:
        _progress["errors"] = _progress["errors"][-100:]


def _finish(status: str, error: Optional[str] = None) -> None:
    with _lock:
        _progress["status"] = status
        _progress["active_lakes"] = 0
        _progress["current_lake_id"] = None
        _progress["current_year"] = None
        _progress["current_tile_index"] = None
        if error:
            _add_error(error)


def fail_imagery_run(message: str) -> None:
    """Mark a claimed run as failed before it started (e.g. queueing failed)."""
    _finish("failed", message)


def _on_lake_start(lake_id: int, year: int) -> None:
    with _lock:
        _progress["active_lakes"] += 1
        _progress["current_lake_id"] = lake_id
        _progress["current_year"] = year
        _progress["current_tile_index"] = None


def _on_tile_complete(lake_id: int, year: int, tile_index: str, result: str) -> None:
    with _lock:
        _progress["current_lake_id"] = lake_id
        _progress["current_year"] = year
        _progress["current_tile_index"] = tile_index
        if result == "completed":
            _progress["tiles_completed"] += 1
        elif result == "failed":
            _progress["tiles_failed"] += 1


def _on_lake_complete(lake_id: int, year: int, result: str, error: Optional[str]) -> None:
    with _lock:
        _progress["active_lakes"] = max(0, _progress["active_lakes"] - 1)
        _progress["processed"] += 1
        if result == "completed":
            _progress["success"] += 1
        elif result == "skipped":
            _progress["skipped"] += 1
        else:
            _progress["failed"] += 1
            _add_error(f"Lake {lake_id}/{year}: {(error or 'download failed')[:200]}")


# ── Public entry point ────────────────────────────────────────────────────


def resolve_run_roots(
    years: List[int],
    requested: Optional[Dict[int, str]] = None,
) -> Dict[int, Path]:
    """Storage root per year for a download run: the requested root, else
    ``SENTINEL_DATA_DIR`` (``backend/data/sentinel``). Files go to
    ``<root>/<year>/``."""
    requested = requested or {}
    return {
        year: Path(requested[year]) if requested.get(year) else default_data_root()
        for year in years
    }


def run_imagery_pipeline(
    lake_ids: Optional[List[int]] = None,
    years: Optional[List[int]] = None,
    year_roots: Optional[Dict[int, str]] = None,
) -> Dict:
    """
    Run the per-lake tile-based Sentinel-2 download pipeline.

    This function runs synchronously (designed for ``BackgroundTasks``).
    Progress is tracked via the global ``_progress`` dict, which
    ``/imagery/status`` reads.

    Args:
        lake_ids: Specific lake IDs to process.  ``None`` = all active.
        years:    List of years.  Required.
        year_roots: Storage root per year for new files. Years not given
                  use ``SENTINEL_DATA_DIR`` (see ``resolve_run_roots``).

    Returns:
        Summary dict with success / failed / skipped counts.
    """
    empty = {"success": 0, "failed": 0, "skipped": 0, "cancelled": False}
    years = years or []

    # Direct callers (scripts) have not claimed the run via the API
    if not is_imagery_active():
        claim_imagery_run({})

    try:
        roots = resolve_run_roots(years, year_roots)
        for root in set(roots.values()):
            validate_data_root(str(root))
        config = get_image_acquisition_config(roots)
        downloader = LakeImageDownloader(config)
        config.ensure_year_dirs(years)

        run_roots = {str(y): str(r) for y, r in roots.items()}
        with _lock:
            _progress["year_roots"] = run_roots

        if lake_ids is None:
            lake_ids = downloader.get_active_lake_ids()
        if not lake_ids:
            logger.warning("No active lakes found — nothing to download")
            _finish("done", "No active lakes to download.")
            return empty
        if not years:
            logger.warning("No years specified — nothing to download")
            _finish("done", "No years selected.")
            return empty
    except Exception as exc:
        logger.exception("Imagery pipeline failed to start", error=str(exc))
        _finish("failed", f"Pipeline error: {str(exc)[:300]}")
        return empty

    total = len(lake_ids) * len(years)
    with _lock:
        _progress["total"] = total

    logger.info(
        "Imagery pipeline started",
        num_lakes=len(lake_ids),
        years=years,
        total_tasks=total,
        year_roots=run_roots,
    )

    def download_one(lake_id: int, year: int) -> str:
        if is_imagery_cancelled():
            return "cancelled"
        _on_lake_start(lake_id, year)
        return downloader.download_lake(
            lake_id,
            year,
            cancel_check=is_imagery_cancelled,
            tile_callback=_on_tile_complete,
        )

    lake_results = {"success": 0, "failed": 0, "skipped": 0}

    try:
        with ThreadPoolExecutor(max_workers=config.lake_workers) as executor:
            futures = {
                executor.submit(download_one, lake_id, year): (lake_id, year)
                for lake_id in lake_ids
                for year in years
            }

            for future in as_completed(futures):
                lake_id, year = futures[future]

                if is_imagery_cancelled():
                    # Drop queued lake-years; in-flight ones finish their tile
                    for f in futures:
                        f.cancel()

                if future.cancelled():
                    continue

                error = None
                try:
                    result = future.result()
                except Exception as exc:
                    logger.exception(
                        "Lake download failed", lake_id=lake_id, year=year, error=str(exc)
                    )
                    result, error = "failed", str(exc)

                if result == "cancelled":
                    continue
                if result == "failed" and is_imagery_cancelled():
                    # Aborted by the user, not a real failure
                    with _lock:
                        _progress["active_lakes"] = max(0, _progress["active_lakes"] - 1)
                    continue
                if result == "failed" and error is None:
                    error = downloader.get_last_error(lake_id, year)

                if result == "completed":
                    lake_results["success"] += 1
                elif result == "skipped":
                    lake_results["skipped"] += 1
                else:
                    lake_results["failed"] += 1

                _on_lake_complete(lake_id, year, result, error)

    except Exception as exc:
        logger.exception("Imagery pipeline failed", error=str(exc))
        _finish("failed", f"Pipeline error: {str(exc)[:300]}")
        return {**lake_results, "cancelled": False}

    cancelled = is_imagery_cancelled()
    final_status = "cancelled" if cancelled else "done"
    _finish(final_status)

    logger.info("Imagery pipeline finished", status=final_status, **lake_results)
    return {**lake_results, "cancelled": cancelled}
