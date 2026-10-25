"""
Embedding pipeline orchestrator.

Processes locally stored 30 m GeoTIFFs, one lake-year at a time:
  lake + shore token windows → Prithvi (selected tokens only) →
    lake / shore pooling → blended embedding, all stored on ``regions``.

Provides global progress state for API polling, cancellation support, and
per-lake-year resumption. ``aggregate_lake_embeddings`` re-blends the
stored lake / shore parts with a new weight without re-running Prithvi.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

import structlog
from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.embedding_pipeline.batch_inference import encode_lake_tokens
from app.embedding_pipeline.config import (
    EmbeddingPipelineConfig,
    get_embedding_pipeline_config,
)
from app.embedding_pipeline.lake_tokens import build_lake_tokens, check_band_stack
from app.embedding_pipeline.storage import EmbeddingStorage
from app.image_acquisition.config import get_image_acquisition_config
from app.models.lake import Lake

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
    "current_step": None,
    "lake_weight": None,
    "errors": [],
}

_cancelled = False

# When True, also check the sync service's cancellation flag
_check_sync_cancel = False

_merge_embedding_progress: Dict = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0,
    "current_lake_id": None,
    "current_year": None,
    "lake_weight": None,
    "errors": [],
}


_ACTIVE_STATUSES = ("running", "cancelling")


def get_embedding_progress() -> Dict:
    """Return a snapshot of the current pipeline progress."""
    with _lock:
        snapshot = dict(_progress)
        snapshot["errors"] = list(_progress["errors"])
        return snapshot


def get_merge_embedding_progress() -> Dict:
    """Return a snapshot of the lake embedding merge progress."""
    with _lock:
        snapshot = dict(_merge_embedding_progress)
        snapshot["errors"] = list(_merge_embedding_progress["errors"])
        return snapshot


def is_embedding_active() -> bool:
    """True while generation runs or is still finishing after cancel."""
    with _lock:
        return _progress["status"] in _ACTIVE_STATUSES


def claim_embedding_run() -> bool:
    """Atomically mark a generation run as started (before it is queued).

    Prevents a stale ``done`` / ``idle`` status right after the request and
    a second run starting while one is active. False if one is active.
    """
    global _cancelled
    with _lock:
        if _progress["status"] in _ACTIVE_STATUSES:
            return False
        if _merge_embedding_progress["status"] == "running":
            return False
        _cancelled = False
        _progress.update(
            status="running",
            total=0,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            current_lake_id=None,
            current_year=None,
            current_step=None,
            lake_weight=None,
            errors=[],
        )
        return True


def claim_merge_run() -> bool:
    """Atomically mark a re-blend as started. False if it would overlap a
    re-blend or an embedding generation run."""
    with _lock:
        if _merge_embedding_progress["status"] == "running":
            return False
        if _progress["status"] in _ACTIVE_STATUSES:
            return False
        _merge_embedding_progress.update(
            status="running",
            total=0,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            current_lake_id=None,
            current_year=None,
            lake_weight=None,
            errors=[],
        )
        return True


def fail_embedding_run(message: str) -> None:
    """Mark a claimed generation run as failed before it started."""
    _finish("failed", message)


def fail_merge_run(message: str) -> None:
    """Mark a claimed re-blend as failed before it started."""
    with _lock:
        _merge_embedding_progress["status"] = "failed"
        _merge_embedding_progress["errors"].append(message)


def cancel_embedding_pipeline() -> bool:
    """Request cancellation; status is ``cancelling`` until the current
    lake-year finishes, then ``cancelled``."""
    global _cancelled
    with _lock:
        if _progress["status"] != "running":
            return False
        _cancelled = True
        _progress["status"] = "cancelling"
    logger.warning("Embedding pipeline cancellation requested")
    return True


def is_embedding_cancelled() -> bool:
    """Check both local and (optionally) sync-service cancellation flags."""
    if _cancelled:
        return True
    if _check_sync_cancel:
        try:
            from app.services.sync_service import is_sync_cancelled  # noqa: PLC0415
            return is_sync_cancelled()
        except Exception:
            pass
    return False


def _finish(status: str, error: Optional[str] = None) -> None:
    with _lock:
        _progress["status"] = status
        _progress["current_lake_id"] = None
        _progress["current_year"] = None
        _progress["current_step"] = None
        if error:
            _progress["errors"].append(error)


def _update_progress(**kwargs) -> None:
    with _lock:
        _progress.update(kwargs)


# ── Synchronous DB engine ─────────────────────────────────────────────────


def _sync_engine():
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
    )


# ── Single lake/year pipeline ─────────────────────────────────────────────


def _process_single_lake(
    lake_id: int,
    year: int,
    config: EmbeddingPipelineConfig,
    storage: EmbeddingStorage,
) -> str:
    """
    Full embedding pipeline for one lake / one year.

    Returns "completed", "skipped", "failed", or "cancelled" (stopped by
    the user before anything was written).
    """
    log = logger.bind(lake_id=lake_id, year=year)

    if is_embedding_cancelled():
        return "cancelled"

    try:
        # ── 1. Resume check ──────────────────────────────────────────────
        _update_progress(current_step="checking_resume")
        if storage.is_completed(lake_id, year):
            log.info("Current-method embedding already stored — skipping")
            return "skipped"

        # ── 2. Look up GeoTIFF path ──────────────────────────────────────
        _update_progress(current_step="loading_geotiff")
        geotiff_path = _get_geotiff_path(lake_id, year, config)
        if geotiff_path is None:
            raise FileNotFoundError(
                f"No merged GeoTIFF found for lake {lake_id} year {year}"
            )
        check_band_stack(str(geotiff_path))
        log.info("Step 1: GeoTIFF located", path=str(geotiff_path))

        # ── 3. Read lake polygon from PostGIS ────────────────────────────
        _update_progress(current_step="reading_polygon")
        lake_polygon = _read_lake_polygon(lake_id)
        if lake_polygon is None:
            raise ValueError(f"Lake {lake_id} has no geometry in PostGIS")

        if is_embedding_cancelled():
            return "cancelled"

        # ── 4. Lake + shore token windows ────────────────────────────────
        _update_progress(current_step="building_token_windows")
        tokens = build_lake_tokens(str(geotiff_path), lake_polygon, config)
        log.info(
            "Step 2: Token windows built",
            windows=len(tokens.windows),
            lake_pixels=tokens.lake_pixels,
            valid_lake_pixels=tokens.valid_lake_pixels,
            shore_pixels=tokens.shore_pixels,
            valid_shore_pixels=tokens.valid_shore_pixels,
        )
        if tokens.valid_lake_pixels < config.min_lake_pixels:
            raise ValueError(
                f"Only {tokens.valid_lake_pixels} valid lake pixels "
                f"(< {config.min_lake_pixels}); composite too cloudy or "
                "lake outside imagery"
            )

        if is_embedding_cancelled():
            return "cancelled"

        # ── 5. Prithvi on lake + shore tokens, pool, blend ───────────────
        _update_progress(current_step="inferring")
        result = encode_lake_tokens(tokens, config.lake_weight)

        if is_embedding_cancelled():
            return "cancelled"

        # ── 6. Store combined embedding + parts on regions ───────────────
        _update_progress(current_step="storing")
        storage.upsert_lake_embeddings(lake_id, year, result)
        log.info(
            "✓ Embedding pipeline completed for lake",
            tokens_encoded=result.tokens_encoded,
            lake_weight=result.lake_weight,
        )
        return "completed"

    except Exception as exc:
        error_msg = str(exc)[:300]
        log.error("✗ Embedding pipeline failed", error=error_msg)
        with _lock:
            _progress["errors"].append(
                f"Lake {lake_id}/{year}: {error_msg}"
            )
            if len(_progress["errors"]) > 100:
                _progress["errors"] = _progress["errors"][-100:]
        try:
            storage.mark_failed(lake_id, year, str(exc))
        except Exception as db_exc:
            log.error("Could not record failure", error=str(db_exc)[:200])
        return "failed"


# ── Helpers ───────────────────────────────────────────────────────────────


def _get_geotiff_path(
    lake_id: int, year: int, config: EmbeddingPipelineConfig
) -> Optional[Path]:
    """Look up the GeoTIFF path from the lake_images table."""
    engine = _sync_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT file_path
                    FROM lake_images
                    WHERE lake_id = :lake_id
                      AND year    = :year
                                            AND status  = 'merged'
                    LIMIT 1
                """),
                {"lake_id": lake_id, "year": year},
            ).fetchone()

        if row is None:
            return None

        full_path = get_image_acquisition_config().resolve_path(row[0])
        return full_path if full_path.is_file() else None
    finally:
        engine.dispose()


def _read_lake_polygon(lake_id: int):
    """Read the lake polygon as a Shapely geometry (EPSG:4326)."""
    engine = _sync_engine()
    Session = sessionmaker(bind=engine)
    try:
        with Session() as session:
            lake = session.execute(
                select(Lake).where(Lake.lake_id == lake_id)
            ).scalar_one_or_none()

            if lake is None or lake.geom is None:
                return None
            return to_shape(lake.geom)
    finally:
        engine.dispose()


# ── Public entry points ───────────────────────────────────────────────────


def run_embedding_pipeline(
    lake_ids: Optional[List[int]] = None,
    years: Optional[List[int]] = None,
    *,
    lake_weight: Optional[float] = None,
    check_sync_cancel: bool = False,
) -> Dict:
    """
    Run the embedding pipeline for specified lakes and years.

    Designed to be called from ``BackgroundTasks`` or from the sync service.
    Progress is tracked via the global ``_progress`` dict.

    Args:
        lake_ids:          Lake IDs to process. If None, auto-discovers from lake_images.
        years:             Years to process.
        lake_weight:       Lake share of the combined embedding. ``None`` uses
                           the weight the stored embeddings already use (so a
                           re-blend is kept consistent), else EMBEDDING_LAKE_WEIGHT.
        check_sync_cancel: When True, also respects the sync service's cancellation
                           flag (used when called from ``start_sync``).
    """
    global _check_sync_cancel
    _check_sync_cancel = check_sync_cancel
    empty = {"success": 0, "failed": 0, "skipped": 0, "cancelled": False}

    # Direct callers (sync service, scripts) have not claimed the run
    if not is_embedding_active():
        claim_embedding_run()

    storage = EmbeddingStorage()
    success = failed = skipped = 0

    try:
        config = get_embedding_pipeline_config()
        if lake_weight is None:
            lake_weight = storage.current_lake_weight()
        if lake_weight is not None:
            if not 0.0 <= lake_weight <= 1.0:
                raise ValueError("lake_weight must be within [0, 1]")
            config = replace(config, lake_weight=float(lake_weight))
        with _lock:
            _progress["lake_weight"] = config.lake_weight

        if not years:
            logger.warning("No years specified")
            _finish("done", "No years selected.")
            return empty

        if lake_ids is None:
            lake_ids = _get_lakes_with_images(years)
            if not lake_ids:
                logger.warning("No lakes with merged images found")
                _finish("done", "No merged lake images found for the selected years.")
                return empty

        total = len(lake_ids) * len(years)
        with _lock:
            _progress["total"] = total

        logger.info(
            "Embedding pipeline started",
            num_lakes=len(lake_ids),
            years=years,
            total_tasks=total,
            lake_weight=config.lake_weight,
        )

        for lake_id in lake_ids:
            for year in years:
                if is_embedding_cancelled():
                    logger.warning("Embedding pipeline cancelled")
                    _finish("cancelled")
                    return {
                        "success": success,
                        "failed": failed,
                        "skipped": skipped,
                        "cancelled": True,
                    }

                _update_progress(current_lake_id=lake_id, current_year=year)

                result = _process_single_lake(lake_id, year, config, storage)

                if result == "cancelled":
                    continue
                if result == "completed":
                    success += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1

                with _lock:
                    _progress["processed"] += 1
                    _progress["success"] = success
                    _progress["failed"] = failed
                    _progress["skipped"] = skipped

        if is_embedding_cancelled():
            _finish("cancelled")
            return {"success": success, "failed": failed, "skipped": skipped, "cancelled": True}

        _finish("done")
        logger.info(
            "Embedding pipeline finished",
            success=success,
            failed=failed,
            skipped=skipped,
        )

    except Exception as exc:
        logger.exception("Embedding pipeline crashed", error=str(exc))
        _finish("failed", f"Pipeline crash: {str(exc)[:300]}")

    finally:
        storage.dispose()
        _check_sync_cancel = False

    return {
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "cancelled": False,
    }


def aggregate_lake_embeddings(
    lake_ids: Optional[List[int]] = None,
    years: Optional[List[int]] = None,
    lake_weight: Optional[float] = None,
) -> Dict:
    """
    Re-blend ``regions.embedding`` from the stored lake / shore parts.

    No Prithvi inference — each row's combined embedding is recomputed as
    ``normalize(w · lake + (1 − w) · shore)``. Use it to apply a new lake
    weight to all lake-years at once (defaults to EMBEDDING_LAKE_WEIGHT).

    Progress is tracked via ``_merge_embedding_progress`` for API polling.

    Returns:
        ``{"success": int, "failed": int, "skipped": int, "total": int}``
    """
    weight = settings.EMBEDDING_LAKE_WEIGHT if lake_weight is None else lake_weight
    storage = EmbeddingStorage()
    with _lock:
        _merge_embedding_progress.update(
            status="running",
            total=0,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            current_lake_id=None,
            current_year=None,
            lake_weight=weight,
            errors=[],
        )

    def _on_total(n: int) -> None:
        with _lock:
            _merge_embedding_progress["total"] = n

    def _on_row(lake_id: int, year: int) -> None:
        with _lock:
            _merge_embedding_progress["processed"] += 1
            _merge_embedding_progress["current_lake_id"] = lake_id
            _merge_embedding_progress["current_year"] = year

    try:
        logger.info("Embedding re-blend started", lake_weight=weight, years=years)
        updated, skipped = storage.reblend(
            weight, years=years, lake_ids=lake_ids, on_row=_on_row, on_total=_on_total
        )
        total = updated + skipped
        with _lock:
            _merge_embedding_progress.update(
                status="done",
                total=total,
                processed=total,
                success=updated,
                skipped=skipped,
                current_lake_id=None,
                current_year=None,
            )
        return {"success": updated, "failed": 0, "skipped": skipped, "total": total}
    except Exception as exc:
        logger.exception("Embedding re-blend crashed", error=str(exc))
        with _lock:
            _merge_embedding_progress["status"] = "failed"
            _merge_embedding_progress["errors"].append(
                f"Re-blend crash: {str(exc)[:300]}"
            )
        raise
    finally:
        storage.dispose()


def _get_lakes_with_images(years: List[int]) -> List[int]:
    """Return lake IDs that have merged GeoTIFFs for any of the given years."""
    engine = _sync_engine()
    try:
        if not years:
            return []
        placeholders = ",".join(str(int(y)) for y in years)
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT DISTINCT lake_id
                    FROM lake_images
                                        WHERE status = 'merged'
                      AND year IN ({placeholders})
                    ORDER BY lake_id
                """)
            ).fetchall()
        return [row[0] for row in rows]
    finally:
        engine.dispose()
