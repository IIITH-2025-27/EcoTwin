"""
High-level entry point for the per-lake tile-based imagery download pipeline.

Manages global progress state so the API can poll ``/imagery/status``
for real-time updates at tile granularity.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

import structlog

from app.image_acquisition.config import get_image_acquisition_config
from app.image_acquisition.downloader import LakeImageDownloader
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = structlog.get_logger(__name__)

# ── Global progress state ─────────────────────────────────────────────────

_lock = threading.Lock()

_progress: Dict = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0,
    "current_lake_id": None,
    "current_year": None,
    "current_tile_index": None,
    "errors": [],
}

_cancelled = False


def get_imagery_progress() -> Dict:
    """Return a snapshot of the current pipeline progress."""
    with _lock:
        return dict(_progress)


def cancel_imagery_pipeline() -> bool:
    """Request cancellation of the running pipeline."""
    global _cancelled
    with _lock:
        if _progress["status"] != "running":
            return False
        _cancelled = True
        _progress["status"] = "cancelled"
    logger.warning("Imagery pipeline cancellation requested")
    return True


def is_imagery_cancelled() -> bool:
    """Return True if cancellation has been requested."""
    return _cancelled


def _reset_progress(total: int) -> None:
    """Reset progress counters for a new run."""
    global _cancelled
    with _lock:
        _cancelled = False
        _progress.update(
            status="running",
            total=total,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            current_lake_id=None,
            current_year=None,
            current_tile_index=None,
            errors=[],
        )


def _on_tile_complete(
    lake_id: int,
    year: int,
    tile_index: str,
    result: str,
    error: Optional[str] = None,
) -> None:
    """Update progress after a single tile completes."""
    with _lock:
        _progress["processed"] += 1
        _progress["current_tile_index"] = None

        if result == "completed":
            _progress["success"] += 1
        elif result == "skipped":
            _progress["skipped"] += 1
        else:
            _progress["failed"] += 1
            if error:
                _progress["errors"].append(
                    f"Lake {lake_id}/{year} tile {tile_index}: {error[:200]}"
                )
                # Cap stored errors
                if len(_progress["errors"]) > 100:
                    _progress["errors"] = _progress["errors"][-100:]


def _on_lake_start(lake_id: int, year: int) -> None:
    """Update progress when starting a new lake/year."""
    with _lock:
        _progress["current_lake_id"] = lake_id
        _progress["current_year"] = year
        _progress["current_tile_index"] = None


def _on_tile_start(tile_index: str) -> None:
    """Update progress when starting a new tile."""
    with _lock:
        _progress["current_tile_index"] = tile_index


def _on_lake_complete(lake_id: int, year: int, result: str) -> None:
    """Update progress when a lake/year is fully done."""
    with _lock:
        _progress["current_lake_id"] = None
        _progress["current_year"] = None
        _progress["current_tile_index"] = None


# ── Public entry point ────────────────────────────────────────────────────


def run_imagery_pipeline(
    lake_ids: Optional[List[int]] = None,
    years: Optional[List[int]] = None,
) -> Dict:
    """
    Run the per-lake tile-based Sentinel-2 download pipeline.

    This function runs synchronously (designed for ``BackgroundTasks``).
    Progress is tracked via the global ``_progress`` dict, which
    ``/imagery/status`` reads.

    Args:
        lake_ids: Specific lake IDs to process.  ``None`` = all active.
        years:    List of years.  Required.

    Returns:
        Summary dict with success / failed / skipped counts.
    """
    config = get_image_acquisition_config()
    config.ensure_data_root()
    downloader = LakeImageDownloader(config)

    # Resolve lake IDs
    if lake_ids is None:
        lake_ids = downloader.get_active_lake_ids()
        if not lake_ids:
            logger.warning("No active lakes found — nothing to download")
            return {"success": 0, "failed": 0, "skipped": 0, "cancelled": False}

    if not years:
        logger.warning("No years specified — nothing to download")
        return {"success": 0, "failed": 0, "skipped": 0, "cancelled": False}

    # We don't know the exact tile count upfront (it varies per lake),
    # so we use lake×year as the total and update dynamically.
    total = len(lake_ids) * len(years)
    _reset_progress(total)

    logger.info(
        "Imagery pipeline started",
        num_lakes=len(lake_ids),
        years=years,
        total_tasks=total,
    )

    def tile_callback(
        lake_id: int, year: int, tile_index: str, result: str
    ) -> None:
        _on_tile_start(tile_index)
        _on_tile_complete(lake_id, year, tile_index, result)

    def lake_callback(lake_id: int, year: int, result: str) -> None:
        _on_lake_complete(lake_id, year, result)

    try:
        lake_results = {"success": 0, "failed": 0, "skipped": 0}

        max_workers = config.lake_workers
        futures = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:

            # Submit all lake/year jobs
            for lake_id in lake_ids:
                for year in years:

                    if is_imagery_cancelled():
                        break

                    # Update currently scheduled lake (for UI)
                    # _on_lake_start(lake_id, year)

                    future = executor.submit(
                        downloader.download_lake_tiles,
                        lake_id,
                        year,
                        cancel_check=is_imagery_cancelled,
                        tile_callback=tile_callback,
                    )

                    futures[future] = (lake_id, year)

                if is_imagery_cancelled():
                    break

            # Process completed jobs
            for future in as_completed(futures):

                if is_imagery_cancelled():
                    break

                lake_id, year = futures[future]

                try:
                    result = future.result()

                except Exception as exc:
                    logger.exception(
                        "Lake download failed",
                        lake_id=lake_id,
                        year=year,
                        error=str(exc),
                    )
                    result = "failed"

                if result == "completed":
                    lake_results["success"] += 1
                elif result == "skipped":
                    lake_results["skipped"] += 1
                else:
                    lake_results["failed"] += 1

                _on_lake_complete(lake_id, year, result)

        final_status = "cancelled" if is_imagery_cancelled() else "done"

        with _lock:
            _progress["status"] = final_status

        summary = {
            **lake_results,
            "cancelled": is_imagery_cancelled(),
        }

        logger.info(
            "Imagery pipeline finished",
            status=final_status,
            **lake_results,
        )

        return summary

    except Exception as exc:
        logger.exception(
            "Imagery pipeline failed",
            error=str(exc),
        )

        with _lock:
            _progress["status"] = "failed"
            _progress["errors"].append(
                f"Pipeline error: {str(exc)[:300]}"
            )

        return {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "cancelled": False,
        }