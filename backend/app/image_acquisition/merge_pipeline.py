"""
Merge pipeline for combining downloaded Sentinel-2 GeoTIFF tiles.

Orchestrates the merge-and-crop workflow for all active lakes,
with global progress tracking for the API to poll.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional

import structlog
# from geoalchemy2.shape import to_shape
from sqlalchemy import select, func
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.image_acquisition.config import get_image_acquisition_config
from app.image_acquisition.storage import root_of_stored_path, summarise_year_roots
from app.image_acquisition.downloader import _is_current_tile, merged_image_is_current
from app.image_acquisition.merger import TileMerger
# from app.models.lake import Lake
from app.models.lake_image import LakeImage
from app.models.lake_tile import LakeTile

logger = structlog.get_logger(__name__)

# ── Global progress state ─────────────────────────────────────────────────

_lock = threading.Lock()

_merge_progress: Dict = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "current_lake_id": None,
    "current_year": None,
    "errors": [],
}


def get_merge_progress() -> Dict:
    """Return a snapshot of the current merge progress."""
    with _lock:
        return dict(_merge_progress)


def _reset_merge_progress(total: int) -> None:
    with _lock:
        _merge_progress.update(
            status="running",
            total=total,
            processed=0,
            success=0,
            failed=0,
            current_lake_id=None,
            current_year=None,
            errors=[],
        )


def _record_merge_result(
    lake_id: int,
    year: int,
    result: str,
    error: Optional[str] = None,
) -> None:
    with _lock:
        _merge_progress["processed"] += 1
        if result == "success":
            _merge_progress["success"] += 1
        else:
            _merge_progress["failed"] += 1
            if error:
                _merge_progress["errors"].append(
                    f"Lake {lake_id}/{year}: {error[:200]}"
                )
                if len(_merge_progress["errors"]) > 100:
                    _merge_progress["errors"] = _merge_progress["errors"][-100:]


# ── Helpers ────────────────────────────────────────────────────────────────


def _sync_engine():
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_mergeable_years() -> List[Dict]:
    """Return years that have completed tiles, with lake counts and the
    folder(s) the merged images will be written to (next to the tiles)."""
    config = get_image_acquisition_config()
    engine = _sync_engine()
    Session = sessionmaker(bind=engine)

    with Session() as session:
        rows = (
            session.execute(
                select(
                    LakeTile.year,
                    func.count(func.distinct(LakeTile.lake_id)).label("lake_count"),
                )
                .where(LakeTile.status == "COMPLETED")
                .group_by(LakeTile.year)
                .order_by(LakeTile.year.desc())
            )
            .all()
        )
        # One path per lake-year is enough to know its root
        tile_paths = session.execute(
            select(LakeTile.year, func.min(LakeTile.image_path), func.max(LakeTile.updated_at))
            .where(LakeTile.status == "COMPLETED")
            .group_by(LakeTile.lake_id, LakeTile.year)
        ).all()

    roots_by_year = summarise_year_roots(tile_paths)
    results = []
    for year, lake_count in rows:
        roots = [e["root"] for e in roots_by_year.get(year, [])] or [config.root_for_year(year)]
        results.append({
            "year": year,
            "lake_count": lake_count,
            "output_path_pattern": " · ".join(
                str(r / str(year) / "lake_{lake_id:06d}.tif") for r in roots
            ),
        })

    return results, str(config.data_root)


# ── Public entry point ────────────────────────────────────────────────────


def run_merge_pipeline(
    years: List[int],
    delete_tiles: bool = False,
    lake_ids: Optional[List[int]] = None,
) -> Dict:
    """
    Merge downloaded tiles for all active lakes across the given years
    (or only ``lake_ids`` when given).

    Runs synchronously (designed for ``BackgroundTasks``).
    Progress is tracked via ``_merge_progress``.
    """
    config = get_image_acquisition_config()
    engine = _sync_engine()
    Session = sessionmaker(bind=engine)
    merger = TileMerger()

    # Find all lake/year combos with completed tiles
    with Session() as session:
        combos = (
            session.execute(
                select(
                    LakeTile.lake_id,
                    LakeTile.year,
                )
                .where(
                    LakeTile.status == "COMPLETED",
                    LakeTile.year.in_(years),
                    *([LakeTile.lake_id.in_(lake_ids)] if lake_ids else []),
                )
                .group_by(LakeTile.lake_id, LakeTile.year)
                .order_by(LakeTile.lake_id, LakeTile.year)
            )
            .all()
        )

    if not combos:
        logger.warning("No completed tiles found for the requested years")
        return {"success": 0, "failed": 0}

    total = len(combos)
    _reset_merge_progress(total)

    logger.info(
        "Merge pipeline started",
        total_tasks=total,
        years=years,
        delete_tiles=delete_tiles,
    )

    results = {"success": 0, "failed": 0, "skipped": 0}

    for lake_id, year in combos:
        with _lock:
            _merge_progress["current_lake_id"] = lake_id
            _merge_progress["current_year"] = year

        try:
            outcome = _merge_single_lake(
                lake_id=lake_id,
                year=year,
                config=config,
                session_factory=Session,
                merger=merger,
                delete_tiles=delete_tiles,
            )
            results["success" if outcome == "merged" else "skipped"] += 1
            # Progress has no "skipped" field; an already-merged lake is done
            _record_merge_result(lake_id, year, "success")

        except Exception as exc:
            error_msg = str(exc)[:500]
            logger.exception(
                "Merge failed for lake/year",
                lake_id=lake_id,
                year=year,
                error=error_msg,
            )
            results["failed"] += 1
            _record_merge_result(lake_id, year, "failed", error=error_msg)

    with _lock:
        _merge_progress["status"] = "done" if results["failed"] == 0 else "failed"
        _merge_progress["current_lake_id"] = None
        _merge_progress["current_year"] = None

    logger.info("Merge pipeline finished", **results)
    return results


def _merge_single_lake(
    lake_id: int,
    year: int,
    config,
    session_factory,
    merger: TileMerger,
    delete_tiles: bool,
) -> str:
    """Merge tiles for a single lake/year combo.

    Returns ``"merged"`` or ``"skipped"`` (current merged image exists).
    """
    log = logger.bind(lake_id=lake_id, year=year)

    # 0. Already merged in the current format (tiles may have been deleted)
    if merged_image_is_current(session_factory, config, lake_id, year):
        log.info("Current merged image exists — skipping merge")
        return "skipped"

    # 1. Every tile of the lake-year must be downloaded — merging a subset
    #    would silently produce an image with holes in the lake.
    with session_factory() as session:
        tile_rows = (
            session.execute(
                select(LakeTile.tile_index, LakeTile.status, LakeTile.image_path)
                .where(
                    LakeTile.lake_id == lake_id,
                    LakeTile.year == year,
                )
            )
            .all()
        )

    if not tile_rows:
        log.warning("No tiles found — skipping")
        return "skipped"

    incomplete = sorted(t for t, st, _ in tile_rows if st != "COMPLETED")
    if incomplete:
        raise RuntimeError(
            f"{len(incomplete)} of {len(tile_rows)} tiles not downloaded "
            f"({incomplete[:5]}); re-run the download before merging"
        )

    tile_paths = [config.resolve_path(rel_path) for _, _, rel_path in tile_rows]
    bad = [str(p) for p in tile_paths if not _is_current_tile(p)]
    if bad:
        raise FileNotFoundError(
            f"{len(bad)} tile file(s) missing or not the current band stack / "
            f"resolution for lake {lake_id} / {year}: {bad[:3]}"
        )

    log.info("Merging tiles", tile_count=len(tile_paths))

    

    # 3. Merge + crop — the merged image goes next to its tiles, i.e. into
    #    the storage root this lake-year was downloaded to.
    tile_roots = [root_of_stored_path(p, year) for _, _, p in tile_rows]
    tile_roots = [r for r in tile_roots if r is not None]
    root = max(set(tile_roots), key=tile_roots.count) if tile_roots else config.root_for_year(year)
    output_path = root / str(year) / config.lake_file_path(lake_id, year).name
    
    merger.merge_tiles_only(
        tile_paths=tile_paths,
        output_path=output_path,
        delete_tiles=delete_tiles,
    )

    # 4. Update lake_images with merged status
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    file_size = output_path.stat().st_size
    rel_output = config.stored_path(output_path)

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    with session_factory() as session:
        stmt = pg_insert(LakeImage).values(
            lake_id=lake_id,
            year=year,
            file_path=rel_output,
            status="merged",
            file_size_bytes=file_size,
            error_message=None,
            retry_count=0,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_lake_images_lake_year",
            set_={
                "status": "merged",
                "file_path": rel_output,
                "file_size_bytes": file_size,
                "error_message": None,
                "updated_at": now,
            },
        )
        session.execute(stmt)
        session.commit()

    log.info(
        "✓ Lake merge completed",
        output=str(output_path),
        file_size=file_size,
    )
    return "merged"
