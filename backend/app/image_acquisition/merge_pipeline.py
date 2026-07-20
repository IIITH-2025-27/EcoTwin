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
    """Return years that have completed tiles, with lake counts."""
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

    results = []
    for year, lake_count in rows:
        results.append({
            "year": year,
            "lake_count": lake_count,
            "output_path_pattern": str(
                config.data_root / str(year) / "lake_{lake_id}.tif"
            ),
        })

    return results, str(config.data_root)


# ── Public entry point ────────────────────────────────────────────────────


def run_merge_pipeline(
    years: List[int],
    delete_tiles: bool = False,
) -> Dict:
    """
    Merge downloaded tiles for all active lakes across the given years.

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

    results = {"success": 0, "failed": 0}

    for lake_id, year in combos:
        with _lock:
            _merge_progress["current_lake_id"] = lake_id
            _merge_progress["current_year"] = year

        try:
            _merge_single_lake(
                lake_id=lake_id,
                year=year,
                config=config,
                session_factory=Session,
                merger=merger,
                delete_tiles=delete_tiles,
            )
            results["success"] += 1
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
) -> None:
    """Merge tiles for a single lake/year combo."""
    log = logger.bind(lake_id=lake_id, year=year)

    # 1. Get completed tile paths
    with session_factory() as session:
        tile_rows = (
            session.execute(
                select(LakeTile.image_path)
                .where(
                    LakeTile.lake_id == lake_id,
                    LakeTile.year == year,
                    LakeTile.status == "COMPLETED",
                )
            )
            .scalars()
            .all()
        )

    if not tile_rows:
        log.warning("No completed tiles found — skipping")
        return

    # Resolve tile paths relative to data_root's grandparent (backend/)
    base_dir = config.data_root.parent.parent
    tile_paths = []
    for rel_path in tile_rows:
        full_path = base_dir / rel_path
        if full_path.is_file():
            tile_paths.append(full_path)
        else:
            log.warning("Tile file missing on disk", path=str(full_path))

    if not tile_paths:
        raise FileNotFoundError(
            f"No tile files found on disk for lake {lake_id} / {year}"
        )

    log.info("Merging tiles", tile_count=len(tile_paths))

    

    # 3. Merge + crop
    output_path = config.lake_file_path(lake_id, year)
    
    merger.merge_tiles_only(
        tile_paths=tile_paths,
        output_path=output_path,
        delete_tiles=delete_tiles,
    )

    # 4. Update lake_images with merged status
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    file_size = output_path.stat().st_size
    rel_output = str(output_path.relative_to(base_dir))

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
