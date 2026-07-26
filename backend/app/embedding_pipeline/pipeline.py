"""
Embedding pipeline orchestrator.

Processes locally stored GeoTIFFs through:
  Grid generation → Cell extraction → GPU-batched Prithvi inference →
    Cell embedding storage in sub_regions.

Provides global progress state for API polling, cancellation support,
and per-cell resumption.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
import structlog
from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.embedding_pipeline.batch_inference import compute_embeddings_batch
from app.embedding_pipeline.cell_extractor import CellExtractor
from app.embedding_pipeline.config import (

    EmbeddingPipelineConfig,
    get_embedding_pipeline_config,
)
from app.embedding_pipeline.grid_generator import GridCell, GridGenerator
from app.embedding_pipeline.storage import EmbeddingStorage
from app.embedding_pipeline.lake_aggregator import (
    aggregate_all_lake_embeddings as _batch_aggregate,
    aggregate_single_lake_year as _single_aggregate,
)
from app.embedding_pipeline.weighted_pooling import weighted_mean_pool
from app.models.lake import Lake
from app.models.lake_image import LakeImage

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
    "errors": [],
}

_cancelled = False

# When True, also check the sync service's cancellation flag
_check_sync_cancel = False


def get_embedding_progress() -> Dict:
    """Return a snapshot of the current pipeline progress."""
    with _lock:
        return dict(_progress)


def cancel_embedding_pipeline() -> bool:
    """Request cancellation of the running pipeline."""
    global _cancelled
    with _lock:
        if _progress["status"] != "running":
            return False
        _cancelled = True
        _progress["status"] = "cancelled"
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


def _reset_progress(total: int) -> None:
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
            current_step=None,
            errors=[],
        )


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

    Returns "completed", "skipped", or "failed".
    """
    log = logger.bind(lake_id=lake_id, year=year)

    if is_embedding_cancelled():
        return "failed"

    try:
        # ── 1. Look up GeoTIFF path ──────────────────────────────────────
        _update_progress(current_step="loading_geotiff")
        geotiff_path = _get_geotiff_path(lake_id, year, config)
        if geotiff_path is None:
            raise FileNotFoundError(
                f"No merged GeoTIFF found for lake {lake_id} year {year}"
            )
        log.info("Step 1: GeoTIFF located", path=str(geotiff_path))

        if is_embedding_cancelled():
            return "failed"

        # ── 2. Read lake polygon from PostGIS ────────────────────────────
        _update_progress(current_step="reading_polygon")
        lake_polygon = _read_lake_polygon(lake_id)
        if lake_polygon is None:
            raise ValueError(f"Lake {lake_id} has no geometry in PostGIS")
        log.info("Step 2: Lake polygon loaded")

        if is_embedding_cancelled():
            return "failed"

        # ── 3. Generate grid ─────────────────────────────────────────────
        _update_progress(current_step="generating_grid")
        grid_gen = GridGenerator(config)
        cells = grid_gen.generate(str(geotiff_path), lake_polygon)
        log.info(
            "Step 3: Grid generated",
            valid_cells=len(cells),
            grid_source="lakes.geom boundary",
            image_usage="pixel extraction for valid cells only",
        )

        if not cells:
            log.warning("No valid grid cells — skipping lake")
            return "skipped"

        if is_embedding_cancelled():
            return "failed"

        # ── 4. Resume check — skip already-completed cells ───────────────
        _update_progress(current_step="checking_resume")
        completed_cells = storage.get_processed_cells(lake_id, year)
        unprocessed = [c for c in cells if c.cell_number not in completed_cells]
        log.info(
            "Step 4: Resume check",
            total_cells=len(cells),
            already_done=len(completed_cells),
            remaining=len(unprocessed),
        )

        if not unprocessed:
            log.info("All valid cells already completed for lake/year — skipping")
            return "skipped"

        # ── 5–8. Extract, infer, store (in GPU batches) ──────────────────
        if unprocessed:
            _update_progress(current_step="extracting_and_inferring")
            extractor = CellExtractor(config)
            batch_size = config.gpu_batch_size

            for batch_start in range(0, len(unprocessed), batch_size):
                if is_embedding_cancelled():
                    return "failed"

                batch_cells = unprocessed[batch_start:batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                total_batches = (len(unprocessed) + batch_size - 1) // batch_size
                log.info(
                    f"Batch {batch_num}/{total_batches}",
                    cells_in_batch=len(batch_cells),
                )

                # Mark cells as processing
                storage.mark_cells_processing(
                    lake_id, year,
                    [c.cell_number for c in batch_cells],
                )

                # 5. Extract cells
                arrays = extractor.extract_batch(str(geotiff_path), batch_cells)

                # Filter out failed extractions
                valid_pairs = [
                    (cell, arr)
                    for cell, arr in zip(batch_cells, arrays)
                    if arr is not None
                ]
                # Mark extraction failures
                failed_extraction_cells = [
                    cell for cell, arr in zip(batch_cells, arrays)
                    if arr is None
                ]
                for cell in failed_extraction_cells:
                    storage.mark_cell_failed(
                        lake_id, cell.cell_number, year,
                        "Cell raster extraction returned empty/invalid data",
                        coverage_percent=cell.coverage_percent,
                        center_lat=cell.center_lat,
                        center_lon=cell.center_lon,
                        bounds_4326=cell.bounds_4326,
                    )

                if not valid_pairs:
                    log.warning("All cells in batch failed extraction")
                    continue

                valid_cells_batch, valid_arrays = zip(*valid_pairs)

                # 6. Batch inference
                embeddings = compute_embeddings_batch(list(valid_arrays))

                # 7. Store each cell embedding
                for cell, emb in zip(valid_cells_batch, embeddings):
                    try:
                        if np.any(emb != 0):
                            storage.upsert_cell_embedding(
                                lake_id=lake_id,
                                cell_number=cell.cell_number,
                                year=year,
                                embedding=emb,
                                coverage_percent=cell.coverage_percent,
                                center_lat=cell.center_lat,
                                center_lon=cell.center_lon,
                                bounds_4326=cell.bounds_4326,
                            )
                        else:
                            storage.mark_cell_failed(
                                lake_id, cell.cell_number, year,
                                "Prithvi returned zero embedding",
                                coverage_percent=cell.coverage_percent,
                                center_lat=cell.center_lat,
                                center_lon=cell.center_lon,
                                bounds_4326=cell.bounds_4326,
                            )
                    except Exception as cell_exc:
                        err_msg = (
                            f"Cell {cell.cell_number} failed for lake {lake_id}/{year}: "
                            f"{str(cell_exc)[:300]}"
                        )
                        log.error("Cell embedding upsert failed", error=err_msg)
                        with _lock:
                            _progress["errors"].append(err_msg)
                            if len(_progress["errors"]) > 100:
                                _progress["errors"] = _progress["errors"][-100:]
                        storage.mark_cell_failed(
                            lake_id, cell.cell_number, year,
                            str(cell_exc)[:500],
                            coverage_percent=cell.coverage_percent,
                            center_lat=cell.center_lat,
                            center_lon=cell.center_lon,
                            bounds_4326=cell.bounds_4326,
                        )

        if is_embedding_cancelled():
            return "failed"

        # Validate at least one completed cell exists after this run.
        _update_progress(current_step="finalizing")
        completed_after = storage.get_processed_cells(lake_id, year)
        if not completed_after:
            log.warning("No completed sub-region embeddings were stored")
            return "failed"

        # ── 9. Aggregate cell embeddings into one lake-level embedding ───
        _update_progress(current_step="aggregating_lake_embedding")
        agg_result = _aggregate_lake_embedding(lake_id, year, storage, log)
        if agg_result == "failed":
            log.warning("Cell embeddings completed but lake-level aggregation failed")
            # cell embeddings are still valid; report as completed

        log.info("✓ Embedding pipeline completed for lake")
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

        # file_path is relative to backend root
        backend_root = Path(__file__).resolve().parents[2]
        full_path = backend_root / row[0]
        return full_path if full_path.is_file() else None
    finally:
        engine.dispose()


def _aggregate_lake_embedding(
    lake_id: int,
    year: int,
    storage: EmbeddingStorage,
    log,
) -> str:
    """
    Fetch completed cell embeddings, compute coverage-weighted mean,
    L2-normalise, and upsert into ``lake_embeddings``.

    Delegates to :func:`lake_aggregator.aggregate_single_lake_year`.

    Returns ``"completed"`` or ``"failed"``.
    """
    engine = _sync_engine()
    Session = sessionmaker(bind=engine)
    try:
        with Session() as session:
            result = _single_aggregate(session, lake_id, year)
        if result.status == "success":
            return "completed"
        log.warning(
            "Lake-level aggregation did not succeed",
            status=result.status,
            reason=result.reason,
        )
        return "failed"
    except Exception as exc:
        log.error("Lake-level aggregation failed", error=str(exc)[:300])
        return "failed"
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
    check_sync_cancel: bool = False,
) -> Dict:
    """
    Run the embedding pipeline for specified lakes and years.

    Designed to be called from ``BackgroundTasks`` or from the sync service.
    Progress is tracked via the global ``_progress`` dict.

    Args:
        lake_ids:          Lake IDs to process. If None, auto-discovers from lake_images.
        years:             Years to process.
        check_sync_cancel: When True, also respects the sync service's cancellation
                           flag (used when called from ``start_sync``).
    """
    global _check_sync_cancel
    _check_sync_cancel = check_sync_cancel

    config = get_embedding_pipeline_config()
    storage = EmbeddingStorage()

    # Resolve lake IDs if not specified
    if lake_ids is None:
        lake_ids = _get_lakes_with_images(years or [])
        if not lake_ids:
            logger.warning("No lakes with downloaded images found")
            return {"success": 0, "failed": 0, "skipped": 0, "cancelled": False}

    if not years:
        logger.warning("No years specified")
        return {"success": 0, "failed": 0, "skipped": 0, "cancelled": False}

    total = len(lake_ids) * len(years)
    _reset_progress(total)

    logger.info(
        "Embedding pipeline started",
        num_lakes=len(lake_ids),
        years=years,
        total_tasks=total,
    )

    success = 0
    failed = 0
    skipped = 0

    try:
        for lake_id in lake_ids:
            for year in years:
                if is_embedding_cancelled():
                    logger.warning("Embedding pipeline cancelled")
                    with _lock:
                        _progress["status"] = "cancelled"
                    storage.dispose()
                    _check_sync_cancel = False
                    return {
                        "success": success,
                        "failed": failed,
                        "skipped": skipped,
                        "cancelled": True,
                    }

                _update_progress(
                    current_lake_id=lake_id,
                    current_year=year,
                )

                result = _process_single_lake(lake_id, year, config, storage)

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

        final_status = "done"
        with _lock:
            _progress["status"] = final_status
            _progress["current_lake_id"] = None
            _progress["current_year"] = None
            _progress["current_step"] = None

        logger.info(
            "Embedding pipeline finished",
            success=success,
            failed=failed,
            skipped=skipped,
        )

    except Exception as exc:
        logger.exception("Embedding pipeline crashed", error=str(exc))
        with _lock:
            _progress["status"] = "failed"
            _progress["errors"].append(f"Pipeline crash: {str(exc)[:300]}")

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
) -> Dict:
    """
    Batch-aggregate cell-level embeddings into lake-level embeddings.

    Delegates to :func:`lake_aggregator.aggregate_all_lake_embeddings`
    which handles discovery, aggregation, and detailed per-pair logging.

    Args:
        lake_ids: Specific lakes to process.  ``None`` = all lakes with
                  completed cell embeddings.
        years:    Specific years to process.  ``None`` = all years with
                  completed cell embeddings.

    Returns:
        ``{"success": int, "failed": int, "skipped": int}``
    """
    batch_result = _batch_aggregate(lake_ids=lake_ids, years=years)
    return batch_result.summary


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
