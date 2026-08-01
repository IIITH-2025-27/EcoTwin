"""Lake feature extraction service.

Orchestrates the end-to-end pipeline: reads merged Sentinel-2 images,
clips them to lake polygons, computes ecological features, and stores
results in the ``lake_features`` table.

Runs **synchronously** (designed for ``BackgroundTasks``), using a sync
SQLAlchemy engine — the same pattern used by the imagery merge pipeline.

This module is intentionally separate from the embedding generation
pipeline.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.lake import Lake
from app.models.lake_feature import LakeFeature
from app.models.lake_image import LakeImage
from app.processing.clipping import clip_raster_to_polygon
from app.processing.spectral_indices import (
    compute_all_indices,
    compute_index_statistics,
)
from app.processing.statistics import (
    compute_band_statistics,
    compute_pixel_statistics,
    compute_spectral_summary,
    compute_water_statistics,
)
from app.processing.texture import compute_glcm_features

logger = structlog.get_logger(__name__)

# ── Thread-safe progress tracking ─────────────────────────────────────────────

_progress_lock = threading.Lock()
_progress: Dict[str, Any] = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "skipped": 0,
    "failed": 0,
    "current_lake_id": None,
    "current_year": None,
    "errors": [],
    "elapsed_seconds": 0.0,
    "processing_rate": 0.0,
    "estimated_remaining_seconds": 0.0,
    "estimated_completion_time": None,
}


def get_feature_progress() -> Dict[str, Any]:
    """Return a snapshot of the current pipeline progress."""
    with _progress_lock:
        return dict(_progress)


def _update_progress(**kwargs: Any) -> None:
    with _progress_lock:
        _progress.update(kwargs)


def _reset_progress(total: int = 0) -> None:
    with _progress_lock:
        _progress.update(
            {
                "status": "running",
                "total": total,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "current_lake_id": None,
                "current_year": None,
                "errors": [],
                "elapsed_seconds": 0.0,
                "processing_rate": 0.0,
                "estimated_remaining_seconds": 0.0,
                "estimated_completion_time": None,
            }
        )


def _update_timing(
    pipeline_start: float,
    completed_count: int,
    total: int,
) -> None:
    """Update elapsed time, processing rate, and ETA in progress state."""
    elapsed = time.monotonic() - pipeline_start
    rate = completed_count / elapsed if elapsed > 0 else 0.0
    remaining_items = total - completed_count
    eta_seconds = remaining_items / rate if rate > 0 else 0.0
    eta_time = (
        datetime.now(timezone.utc).isoformat()
        if remaining_items == 0
        else (
            datetime.fromtimestamp(
                time.time() + eta_seconds, tz=timezone.utc
            ).isoformat()
        )
    )

    _update_progress(
        elapsed_seconds=round(elapsed, 2),
        processing_rate=round(rate, 4),
        estimated_remaining_seconds=round(eta_seconds, 1),
        estimated_completion_time=eta_time,
    )


# ── Sync DB helpers (same pattern as merge_pipeline.py) ───────────────────────


def _sync_engine():
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


# ── Stage timer helper ────────────────────────────────────────────────────────


class _StageTimer:
    """Context manager that records elapsed time for a named stage."""

    def __init__(self) -> None:
        self.timings: Dict[str, float] = {}
        self._start: float = 0.0
        self._name: str = ""

    def stage(self, name: str) -> "_StageTimer":
        self._name = name
        return self

    def __enter__(self) -> "_StageTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.timings[self._name] = round(time.monotonic() - self._start, 4)

    def log_summary(self, log: Any, lake_id: int, year: int) -> None:
        parts = [f"{k}={v:.2f}s" for k, v in self.timings.items()]
        log.info(
            "Stage timings",
            lake_id=lake_id,
            year=year,
            **self.timings,
            summary=" | ".join(parts),
        )


# ── Main pipeline entry point ─────────────────────────────────────────────────


def generate_lake_features(
    year: Optional[int] = None,
    overwrite: bool = False,
) -> Dict[str, int]:
    """Run the full lake feature extraction pipeline.

    Runs **synchronously** — designed to be called via
    ``BackgroundTasks.add_task()``.

    Parameters
    ----------
    year : If provided, only process merged images for this year.
    overwrite : If True, re-compute features even if they already exist.

    Returns
    -------
    Dict with total, processed, skipped, failed counts.
    """
    engine = _sync_engine()
    Session = sessionmaker(bind=engine)

    try:
        # ── Fetch all merged images ───────────────────────────────────────
        with Session() as session:
            stmt = select(LakeImage).where(LakeImage.status == "merged")
            if year is not None:
                stmt = stmt.where(LakeImage.year == year)
            stmt = stmt.order_by(LakeImage.lake_id, LakeImage.year)
            images = list(session.execute(stmt).scalars().all())

        total = len(images)

        logger.info(
            "Lake feature generation started",
            total_images=total,
            year=year,
            overwrite=overwrite,
        )

        _reset_progress(total=total)
        pipeline_start = time.monotonic()

        processed = 0
        skipped = 0
        failed = 0
        errors: List[str] = []

        for img in images:
            lake_id = img.lake_id
            img_year = img.year
            file_path = img.file_path

            _update_progress(
                current_lake_id=lake_id,
                current_year=img_year,
            )

            # ── One session per lake — commit on success, rollback on failure ──
            session = Session()
            try:
                # Step 1: Skip if features exist and no overwrite
                if not overwrite:
                    existing = session.execute(
                        select(LakeFeature).where(
                            LakeFeature.lake_id == lake_id,
                            LakeFeature.year == img_year,
                            LakeFeature.status == "completed",
                        )
                    ).scalar_one_or_none()

                    if existing is not None:
                        logger.info(
                            "Skipping (features exist)",
                            lake_id=lake_id,
                            year=img_year,
                        )
                        skipped += 1
                        completed = processed + skipped + failed
                        _update_progress(processed=completed, skipped=skipped)
                        _update_timing(pipeline_start, completed, total)
                        session.close()
                        continue

                timer = _StageTimer()
                t0 = time.monotonic()
                logger.info(
                    "Processing lake",
                    lake_id=lake_id,
                    year=img_year,
                )

                # Step 2: Fetch polygon
                with timer.stage("fetch_polygon"):
                    lake = session.execute(
                        select(Lake).where(Lake.lake_id == lake_id)
                    ).scalar_one_or_none()

                    if lake is None or lake.geom is None:
                        raise ValueError(
                            f"Lake {lake_id} not found or has no geometry"
                        )

                    # Convert WKBElement → Shapely while session is open
                    lake_shape = to_shape(lake.geom)

                # Step 3 & 4: Open raster and clip
                with timer.stage("clip_raster"):
                    clipped = clip_raster_to_polygon(
                        file_path=file_path,
                        lake_shape=lake_shape,
                        geom_srid=4326,
                    )
                    bands = clipped.data  # (6, H, W) float32

                    if bands.shape[0] < 6:
                        raise ValueError(
                            f"Expected 6 bands, got {bands.shape[0]}"
                        )

                # Step 5: Band statistics (now includes median)
                with timer.stage("band_statistics"):
                    band_stats = compute_band_statistics(bands, clipped.nodata)

                # Step 6 & 7: Spectral indices + statistics
                with timer.stage("spectral_indices"):
                    indices = compute_all_indices(bands, clipped.nodata)

                    index_features: Dict[str, Any] = {}

                    # NDVI — full stats (mean/std/min/max/median/p25/p75)
                    ndvi_stats = compute_index_statistics(
                        indices["ndvi"], full_stats=True
                    )
                    for k, v in ndvi_stats.items():
                        index_features[f"ndvi_{k}"] = v

                    # NDWI — full stats
                    ndwi_stats = compute_index_statistics(
                        indices["ndwi"], full_stats=True
                    )
                    for k, v in ndwi_stats.items():
                        index_features[f"ndwi_{k}"] = v

                    # EVI — mean + std
                    evi_stats = compute_index_statistics(indices["evi"])
                    index_features["evi_mean"] = evi_stats["mean"]
                    index_features["evi_std"] = evi_stats["std"]

                    # SAVI — mean + std
                    savi_stats = compute_index_statistics(indices["savi"])
                    index_features["savi_mean"] = savi_stats["mean"]
                    index_features["savi_std"] = savi_stats["std"]

                    # Single-stat indices — mean only
                    for idx_name in [
                        "msavi", "gci", "ndre", "mndwi", "ndmi", "awei",
                        "bsi", "ndbi",
                    ]:
                        stats = compute_index_statistics(indices[idx_name])
                        index_features[f"{idx_name}_mean"] = stats["mean"]

                    # NBR — mean + std
                    nbr_stats = compute_index_statistics(indices["nbr"])
                    index_features["nbr_mean"] = nbr_stats["mean"]
                    index_features["nbr_std"] = nbr_stats["std"]

                    # NBR2 — mean only
                    nbr2_stats = compute_index_statistics(indices["nbr2"])
                    index_features["nbr2_mean"] = nbr2_stats["mean"]

                # Step 8: Texture features
                with timer.stage("texture"):
                    texture_features = compute_glcm_features(
                        bands, nodata=clipped.nodata
                    )

                # Step 9: Spectral summary
                with timer.stage("spectral_summary"):
                    spectral_summary = compute_spectral_summary(
                        bands, nodata=clipped.nodata
                    )

                # Step 10: Pixel statistics
                with timer.stage("pixel_statistics"):
                    pixel_stats = compute_pixel_statistics(
                        bands, nodata=clipped.nodata
                    )

                # Step 11: Water statistics (now uses MNDWI + improved area calc)
                with timer.stage("water_statistics"):
                    water_stats = compute_water_statistics(
                        ndwi_array=indices["ndwi"],
                        mndwi_array=indices["mndwi"],
                        ndvi_array=indices["ndvi"],
                        pixel_size_x=clipped.pixel_size_x,
                        pixel_size_y=clipped.pixel_size_y,
                        crs=str(clipped.crs),
                        raster_transform=clipped.transform,
                    )

                # Step 12: Assemble and save
                now = datetime.now(timezone.utc)
                all_features: Dict[str, Any] = {
                    "status": "completed",
                    "error_message": None,
                    "updated_at": now,
                    **band_stats,
                    **index_features,
                    **texture_features,
                    **spectral_summary,
                    **pixel_stats,
                    **water_stats,
                }

                with timer.stage("db_save"):
                    if overwrite:
                        # PostgreSQL upsert
                        stmt = pg_insert(LakeFeature).values(
                            lake_id=lake_id,
                            year=img_year,
                            created_at=now,
                            **all_features,
                        )
                        update_cols = {
                            k: v
                            for k, v in all_features.items()
                        }
                        stmt = stmt.on_conflict_do_update(
                            constraint="uq_lake_features_lake_year",
                            set_=update_cols,
                        )
                        session.execute(stmt)
                    else:
                        feature = LakeFeature(
                            lake_id=lake_id,
                            year=img_year,
                            created_at=now,
                            **all_features,
                        )
                        session.add(feature)
                    session.commit()

                elapsed = time.monotonic() - t0
                processed += 1
                completed = processed + skipped + failed
                _update_progress(processed=completed)
                _update_timing(pipeline_start, completed, total)

                # Log per-stage timings
                timer.log_summary(logger, lake_id, img_year)

                logger.info(
                    "Completed lake feature extraction",
                    lake_id=lake_id,
                    year=img_year,
                    elapsed_seconds=round(elapsed, 2),
                )

            except Exception as exc:
                session.rollback()
                failed += 1
                error_msg = f"Lake {lake_id} ({img_year}): {exc}"
                errors.append(error_msg)
                completed = processed + skipped + failed
                _update_progress(
                    processed=completed,
                    failed=failed,
                    errors=errors[-10:],
                )
                _update_timing(pipeline_start, completed, total)

                logger.error(
                    "Failed to process lake",
                    lake_id=lake_id,
                    year=img_year,
                    error=str(exc),
                )

                # Mark as failed in DB (same session, already rolled back)
                try:
                    existing = session.execute(
                        select(LakeFeature).where(
                            LakeFeature.lake_id == lake_id,
                            LakeFeature.year == img_year,
                        )
                    ).scalar_one_or_none()

                    if existing:
                        existing.status = "failed"
                        existing.error_message = str(exc)
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        session.add(LakeFeature(
                            lake_id=lake_id,
                            year=img_year,
                            status="failed",
                            error_message=str(exc),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                        ))
                    session.commit()
                except Exception as db_err:
                    session.rollback()
                    logger.error(
                        "Failed to mark lake as failed in DB",
                        lake_id=lake_id,
                        error=str(db_err),
                    )

                # Continue processing remaining lakes
                continue
            finally:
                session.close()

        total_elapsed = time.monotonic() - pipeline_start
        _update_progress(
            status="done",
            current_lake_id=None,
            current_year=None,
            elapsed_seconds=round(total_elapsed, 2),
            estimated_remaining_seconds=0.0,
            estimated_completion_time=datetime.now(timezone.utc).isoformat(),
        )

        result = {
            "total": total,
            "processed": processed,
            "skipped": skipped,
            "failed": failed,
        }

        logger.info(
            "Lake feature generation complete",
            elapsed_seconds=round(total_elapsed, 2),
            **result,
        )
        return result

    except Exception as exc:
        logger.exception("Lake feature pipeline failed", error=str(exc))
        _update_progress(
            status="failed",
            errors=[str(exc)],
            current_lake_id=None,
            current_year=None,
        )
        return {
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
        }
    finally:
        engine.dispose()
