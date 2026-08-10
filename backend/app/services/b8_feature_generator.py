"""B8 (NIR, 842nm) band statistics extraction service.

Computes Sentinel-2 B8 zonal statistics (mean/std/median) entirely
server-side via Earth Engine's ``reduceRegions()`` — no GeoTIFF is ever
downloaded, clipped, or read into a NumPy array. This is the key
difference from the B2-B7 pipeline (which downloads/clips/reduces
locally): reduceRegions batches many lake polygons against one composite
in a single Earth Engine call and returns only the reduced numbers.

B8 is fetched separately from the standard B2-B7 acquisition pipeline
since it's intentionally excluded from the Prithvi band set
(``S2_BANDS_PRITHVI`` in ``app/ML_pipeline/constants.py``) used for
embeddings — appending it there would break Prithvi inference (wrong band
count / normalization). This module never touches that pipeline; results
are written into the existing ``lake_features`` row for the same lake/year
(``b8_mean`` / ``b8_std`` / ``b8_median`` / ``b8_status`` columns, added in
migrations 018-019).

Runs **synchronously** (designed for ``BackgroundTasks``).

Only processes lakes where ``lakes.is_active`` is true and a completed
``lake_features`` row already exists for that lake/year — B8 stats enrich
existing feature rows, they never create new ones.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog
from geoalchemy2.shape import to_shape
from sqlalchemy import select, update
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.image_acquisition.config import get_image_acquisition_config
from app.image_acquisition.gee_helper import SentinelCompositeBuilder
from app.models.lake import Lake
from app.models.lake_feature import LakeFeature

logger = structlog.get_logger(__name__)

_B8_BANDS = ["B8"]

# Lakes per reduceRegions() call. Keeps each server-side call and its
# getInfo() response small/fast and avoids Earth Engine per-request
# computation limits; tuned conservatively, not maximised.
_REDUCE_BATCH_SIZE = 10

# reduceRegions() retry settings for transient Earth Engine errors.
_REDUCE_MAX_RETRIES = 3
_REDUCE_RETRY_DELAY_SEC = 5.0
_REDUCE_RETRY_BACKOFF = 2.0

# ── Thread-safe progress tracking (separate from the B2-B7 pipeline) ──────────

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


def get_b8_feature_progress() -> Dict[str, Any]:
    """Return a snapshot of the current B8 pipeline progress."""
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


def _update_timing(pipeline_start: float, completed_count: int, total: int) -> None:
    elapsed = time.monotonic() - pipeline_start
    rate = completed_count / elapsed if elapsed > 0 else 0.0
    remaining_items = total - completed_count
    eta_seconds = remaining_items / rate if rate > 0 else 0.0
    eta_time = (
        datetime.now(timezone.utc).isoformat()
        if remaining_items == 0
        else datetime.fromtimestamp(time.time() + eta_seconds, tz=timezone.utc).isoformat()
    )
    _update_progress(
        elapsed_seconds=round(elapsed, 2),
        processing_rate=round(rate, 4),
        estimated_remaining_seconds=round(eta_seconds, 1),
        estimated_completion_time=eta_time,
    )


def _sync_engine():
    return create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)


def _chunked(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _reduce_batch(
    ee: Any,
    composite: Any,
    scale: int,
    batch: List[Tuple[int, dict]],
) -> Dict[int, Dict[str, Optional[float]]]:
    """Run one server-side reduceRegions() call for a batch of lakes.

    Parameters
    ----------
    batch : list of (lake_id, geojson_geometry) for lakes to reduce this call.

    Returns
    -------
    Dict of lake_id -> {"b8_mean", "b8_std", "b8_median", "b8_min", "b8_max"}
    (values may be None if a lake had no valid pixels, e.g. fully cloud-masked).
    """
    features = [
        ee.Feature(ee.Geometry(geom), {"lake_id": lake_id})
        for lake_id, geom in batch
    ]
    fc = ee.FeatureCollection(features)

    reducer = (
        ee.Reducer.mean()
        .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True)
        .combine(reducer2=ee.Reducer.median(), sharedInputs=True)
        .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
    )

    reduced = composite.reduceRegions(
        collection=fc,
        reducer=reducer,
        scale=scale,
        tileScale=4,
    )
    # Drop geometry from the response — only the reduced numbers are needed,
    # and this keeps the getInfo() payload small.
    reduced = reduced.select(["lake_id", "mean", "stdDev", "median", "min", "max"], None, False)

    delay = _REDUCE_RETRY_DELAY_SEC
    last_error: Optional[Exception] = None
    for attempt in range(1, _REDUCE_MAX_RETRIES + 1):
        try:
            info = reduced.getInfo()
            break
        except Exception as exc:  # noqa: BLE001 — Earth Engine raises various error types
            last_error = exc
            if attempt < _REDUCE_MAX_RETRIES:
                logger.warning(
                    "reduceRegions batch failed — retrying",
                    attempt=attempt, error=str(exc), retry_in_sec=delay,
                )
                time.sleep(delay)
                delay *= _REDUCE_RETRY_BACKOFF
            else:
                raise RuntimeError(
                    f"reduceRegions failed after {_REDUCE_MAX_RETRIES} attempts: {exc}"
                ) from last_error
    else:
        raise RuntimeError(f"reduceRegions failed: {last_error}")

    out: Dict[int, Dict[str, Optional[float]]] = {}
    for feat in info.get("features", []):
        props = feat.get("properties", {})
        lake_id = int(props["lake_id"])
        out[lake_id] = {
            "b8_mean": props.get("mean"),
            "b8_std": props.get("stdDev"),
            "b8_median": props.get("median"),
            "b8_min": props.get("min"),
            "b8_max": props.get("max"),
        }
    return out


def generate_b8_features(
    year: Optional[int] = None,
    overwrite: bool = False,
) -> Dict[str, int]:
    """Compute B8 zonal statistics for active lakes' existing feature rows.

    All computation happens server-side on Earth Engine via
    ``Image.reduceRegions()`` — no imagery is downloaded to this process.

    Parameters
    ----------
    year : If provided, only process feature rows for this year. If None,
        all years are processed.
    overwrite : If True, re-compute B8 even for rows already marked "completed".

    Returns
    -------
    Dict with total, processed, skipped, failed counts.
    """
    # Mark "running" before anything else — including Earth Engine init and
    # engine/session setup — so that a failure at any point (e.g. GEE auth)
    # is visible as status="failed" rather than leaving _progress stuck at
    # its previous state (e.g. "idle" forever, if this is the first run).
    _reset_progress(total=0)

    processed = 0
    skipped = 0
    failed = 0
    errors: List[str] = []

    try:
        engine = _sync_engine()
        Session = sessionmaker(bind=engine)
        cfg = get_image_acquisition_config()
        gee = SentinelCompositeBuilder(cfg)
        ee = gee.ee_module

        with Session() as session:
            stmt = (
                select(LakeFeature.lake_id, LakeFeature.year, LakeFeature.b8_status)
                .join(Lake, Lake.lake_id == LakeFeature.lake_id)
                .where(Lake.is_active.is_(True), LakeFeature.status == "completed")
            )
            if year is not None:
                stmt = stmt.where(LakeFeature.year == year)
            stmt = stmt.order_by(LakeFeature.year, LakeFeature.lake_id)
            targets = list(session.execute(stmt).all())

        total = len(targets)
        logger.info("B8 feature generation started", total_targets=total, year=year, overwrite=overwrite)

        _reset_progress(total=total)
        pipeline_start = time.monotonic()

        # Group by year — one composite is built and reused across every
        # lake for that year, instead of one fetch per lake.
        by_year: Dict[int, List[int]] = {}
        status_by_key: Dict[Tuple[int, int], str] = {}
        for lake_id, feat_year, existing_status in targets:
            status_by_key[(lake_id, feat_year)] = existing_status
            by_year.setdefault(feat_year, []).append(lake_id)

        for feat_year in sorted(by_year):
            lake_ids_needing = [
                lid for lid in by_year[feat_year]
                if overwrite or status_by_key[(lid, feat_year)] != "completed"
            ]
            already_done = len(by_year[feat_year]) - len(lake_ids_needing)
            if already_done:
                skipped += already_done
                completed = processed + skipped + failed
                _update_progress(skipped=skipped)
                _update_timing(pipeline_start, completed, total)

            if not lake_ids_needing:
                continue

            with Session() as session:
                lake_rows = session.execute(
                    select(Lake.lake_id, Lake.geom).where(Lake.lake_id.in_(lake_ids_needing))
                ).all()

            geoms: Dict[int, dict] = {}
            bounds: List[Tuple[float, float, float, float]] = []
            for lake_id, geom in lake_rows:
                if geom is None:
                    continue
                shape = to_shape(geom)
                geoms[lake_id] = shape.__geo_interface__
                bounds.append(shape.bounds)

            missing_geom = set(lake_ids_needing) - set(geoms)
            for lake_id in missing_geom:
                errors.append(f"lake {lake_id} year {feat_year}: no geometry")
                failed += 1
                _mark_status(Session, lake_id, feat_year, "failed")

            if not geoms:
                completed = processed + skipped + failed
                _update_progress(processed=processed, skipped=skipped, failed=failed, errors=errors[-20:])
                _update_timing(pipeline_start, completed, total)
                continue

            union_bounds = (
                min(b[0] for b in bounds), min(b[1] for b in bounds),
                max(b[2] for b in bounds), max(b[3] for b in bounds),
            )
            aoi = gee.build_aoi_from_bbox(*union_bounds)
            composite = gee.build_composite(aoi, feat_year, bands=_B8_BANDS)

            for batch_lake_ids in _chunked(list(geoms.keys()), _REDUCE_BATCH_SIZE):
                _update_progress(current_lake_id=batch_lake_ids[0], current_year=feat_year)
                batch = [(lid, geoms[lid]) for lid in batch_lake_ids]

                try:
                    results = _reduce_batch(ee, composite, cfg.scale_metres, batch)
                except Exception as exc:
                    error_msg = f"year {feat_year} batch {batch_lake_ids[:3]}...: {exc}"[:500]
                    logger.error("B8 reduceRegions batch failed", year=feat_year, lake_ids=batch_lake_ids, error=str(exc))
                    errors.append(error_msg)
                    for lake_id in batch_lake_ids:
                        failed += 1
                        _mark_status(Session, lake_id, feat_year, "failed")
                    completed = processed + skipped + failed
                    _update_progress(processed=processed, skipped=skipped, failed=failed, errors=errors[-20:])
                    _update_timing(pipeline_start, completed, total)
                    continue

                now = datetime.now(timezone.utc)
                with Session() as session:
                    for lake_id in batch_lake_ids:
                        stats = results.get(lake_id)
                        if stats is None or stats.get("b8_mean") is None:
                            failed += 1
                            session.execute(
                                update(LakeFeature)
                                .where(LakeFeature.lake_id == lake_id, LakeFeature.year == feat_year)
                                .values(b8_status="failed")
                            )
                            errors.append(f"lake {lake_id} year {feat_year}: no valid B8 pixels")
                        else:
                            processed += 1
                            session.execute(
                                update(LakeFeature)
                                .where(LakeFeature.lake_id == lake_id, LakeFeature.year == feat_year)
                                .values(**stats, b8_status="completed", updated_at=now)
                            )
                    session.commit()

                logger.info(
                    "B8 batch reduced",
                    year=feat_year, lake_count=len(batch_lake_ids),
                )

                completed = processed + skipped + failed
                _update_progress(processed=processed, skipped=skipped, failed=failed, errors=errors[-20:])
                _update_timing(pipeline_start, completed, total)

        _update_progress(status="done")
        logger.info(
            "B8 feature generation completed",
            total=total, processed=processed, skipped=skipped, failed=failed,
        )
        return {"total": total, "processed": processed, "skipped": skipped, "failed": failed}

    except Exception as exc:
        logger.error("B8 feature generation failed", error=str(exc))
        errors.append(str(exc)[:500])
        _update_progress(
            status="failed",
            processed=processed, skipped=skipped, failed=failed,
            errors=errors[-20:],
        )
        raise
    finally:
        if "engine" in locals():
            engine.dispose()


def _mark_status(Session, lake_id: int, year: int, status_value: str) -> None:
    with Session() as session:
        session.execute(
            update(LakeFeature)
            .where(LakeFeature.lake_id == lake_id, LakeFeature.year == year)
            .values(b8_status=status_value)
        )
        session.commit()
