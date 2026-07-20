"""
Per-lake tile-based Sentinel-2 GeoTIFF downloader.

Orchestrates the full pipeline for a single lake:
  1. Read lake polygon from PostGIS.
  2. Convert to projected CRS → buffer → convert back to EPSG:4326.
  3. Compute bounding box.
  4. Generate 10 km × 10 km tile grid over the buffered region.
  5. Build Sentinel-2 composite via Earth Engine (once per lake).
  6. Download one GeoTIFF per intersecting tile.
  7. Upsert metadata rows in the ``lake_tiles`` table.
  8. Update the parent ``lake_images`` row with aggregate status.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog
from geoalchemy2.shape import to_shape
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.image_acquisition.config import AcquisitionMode, ImageAcquisitionConfig
from app.image_acquisition.gee_helper import SentinelCompositeBuilder
from app.image_acquisition.grid import TileInfo, generate_tile_grid
from app.models.lake import Lake
from app.models.lake_image import LakeImage
from app.models.lake_tile import LakeTile
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 4
logger = structlog.get_logger(__name__)


def _sync_engine():
    """Create a synchronous engine for use in background threads."""
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


class LakeImageDownloader:
    """Download Sentinel-2 GeoTIFFs for lakes using a tile-based grid."""

    def __init__(self, config: ImageAcquisitionConfig) -> None:
        self._cfg = config
        self._engine = _sync_engine()
        self._Session = sessionmaker(bind=self._engine)
        self._gee: Optional[SentinelCompositeBuilder] = None

    @property
    def gee(self) -> SentinelCompositeBuilder:
        """Lazy-initialise the GEE helper (avoids import-time ``ee.Initialize``)."""
        if self._gee is None:
            self._gee = SentinelCompositeBuilder(self._cfg)
        return self._gee

    # ── Mode-aware dispatcher ─────────────────────────────────────────────

    def download_lake(
        self,
        lake_id: int,
        year: int,
        *,
        cancel_check: Optional[Callable] = None,
        tile_callback: Optional[Callable] = None,
    ) -> str:
        """
        Download imagery for one lake / one year using the configured mode.

        Dispatches to :meth:`download_lake_tiles` (tile-by-tile via
        ``getDownloadURL``) or :meth:`download_lake_drive`
        (``Export.image.toDrive``) depending on
        ``self._cfg.mode``.

        Args:
            lake_id: HydroLAKES lake ID.
            year: Target year.
            cancel_check: Returns ``True`` to abort.
            tile_callback: Called after each tile *(tile mode only)*.

        Returns:
            ``"completed"``, ``"skipped"``, or ``"failed"``.
        """
        if self._cfg.mode == AcquisitionMode.TILE:
            return self.download_lake_tiles(
                lake_id,
                year,
                cancel_check=cancel_check,
                tile_callback=tile_callback,
            )

        if self._cfg.mode == AcquisitionMode.DRIVE:
            return self.download_lake_drive(
                lake_id,
                year,
                cancel_check=cancel_check,
            )

        raise ValueError(f"Unsupported acquisition mode: {self._cfg.mode!r}")

    # ── Single-lake tile pipeline ─────────────────────────────────────────

    def download_lake_tiles(
        self,
        lake_id: int,
        year: int,
        *,
        cancel_check: Optional[Callable] = None,
        tile_callback: Optional[Callable] = None,
    ) -> str:
        """
        Full tile-based download pipeline for one lake / one year.

        Args:
            lake_id: The HydroLAKES lake ID.
            year: The target year.
            cancel_check: Returns True to abort.
            tile_callback: Called after each tile with
                ``(lake_id, year, tile_index, result)`` where result is
                ``"completed"``, ``"skipped"``, or ``"failed"``.

        Returns:
            ``"completed"``, ``"skipped"`` (all tiles already done),
            or ``"failed"``.
        """
        log = logger.bind(lake_id=lake_id, year=year)

        try:
            # 1. Read lake polygon from PostGIS
            log.info("Step 1: Reading lake polygon from PostGIS")
            geom_4326 = self._read_lake_polygon(lake_id)
            if geom_4326 is None:
                raise ValueError(f"Lake {lake_id} has no geometry in PostGIS")

            if cancel_check and cancel_check():
                return "failed"

            # 2-3. Convert to projected CRS, buffer, convert back
            log.info(
                "Step 2-4: Projecting → buffering → reprojecting",
                buffer_m=self._cfg.buffer_distance_m,
            )
            buffered_geom = self._buffer_polygon(geom_4326)

            # 4. Generate tile grid
            log.info(
                "Step 4: Generating tile grid",
                tile_size_m=self._cfg.tile_size_m,
            )
            tiles = generate_tile_grid(
                buffered_geom,
                self._cfg.tile_size_m,
                self._cfg.projected_crs,
            )
            log.info("Tile grid generated", num_tiles=len(tiles))

            if not tiles:
                log.warning("No intersecting tiles found — skipping")
                return "skipped"

            # 5. Upsert PENDING rows for all tiles
            self._ensure_tile_rows(lake_id, year, tiles)

            # 6. Filter to tiles not yet completed
            pending_indices = self._get_pending_tile_indices(lake_id, year)
            if not pending_indices:
                log.info("All tiles already completed — skipping")
                self._update_lake_image_aggregate(lake_id, year)
                return "skipped"

            pending_tiles = [t for t in tiles if t.tile_index in pending_indices]
            log.info(
                "Tiles to download",
                pending=len(pending_tiles),
                total=len(tiles),
            )

            if cancel_check and cancel_check():
                return "failed"

            # 7. Build composite ONCE for the full buffered extent
            full_bbox = buffered_geom.bounds  # (minx, miny, maxx, maxy)
            log.info(
                "Step 6-9: Building Sentinel-2 composite via GEE (once)",
                west=full_bbox[0],
                south=full_bbox[1],
                east=full_bbox[2],
                north=full_bbox[3],
            )
            full_aoi = self.gee.build_aoi_from_bbox(*full_bbox)
            composite = self.gee.build_composite(full_aoi, year)

            if cancel_check and cancel_check():
                return "failed"

            # 8. Download each pending tile
            any_failed = False
            with ThreadPoolExecutor(max_workers=self._cfg.download_workers) as executor:
                future_map = {
                    executor.submit(
                        self._download_single_tile,
                        lake_id,
                        year,
                        tile,
                        composite,
                    ): tile
                    for tile in pending_tiles
                }
            
                for future in as_completed(future_map):
                    if cancel_check and cancel_check():
                        for f in future_map:
                            f.cancel()
                        executor.shutdown(wait=False, cancel_futures=True)
                        return "failed"
                    
                    tile = future_map[future]
                
                    try:
                        result = future.result()
                
                    except Exception as exc:
                        log.exception(
                            "Parallel tile download failed",
                            tile=tile.tile_index,
                            error=str(exc),
                        )
                        result = "failed"
            
                    if result == "failed":
                        any_failed = True
            
                    if tile_callback:
                        tile_callback(
                            lake_id,
                            year,
                            tile.tile_index,
                            result,
                        )

            # 9. Update parent lake_images with aggregate status
            self._update_lake_image_aggregate(lake_id, year)

            if any_failed:
                log.warning("Some tiles failed")
                return "failed"

            log.info("✓ All tiles downloaded successfully")
            return "completed"

        except Exception as exc:
            error_msg = str(exc)[:500]
            log.error("✗ Lake tile download failed", error=error_msg)
            self._upsert_lake_image_status(
                lake_id,
                year,
                "failed",
                error_message=error_msg,
            )
            return "failed"

    def _download_single_tile(
        self,
        lake_id: int,
        year: int,
        tile: TileInfo,
        composite: Any,
    ) -> str:
        """Download a single tile GeoTIFF from the prebuilt composite."""
        log = logger.bind(
            lake_id=lake_id, year=year, tile_index=tile.tile_index
        )
        log.info("Downloading tile")

        try:
            # Mark as downloading
            self._upsert_tile_status(lake_id, year, tile.tile_index, "DOWNLOADING")

            # Build tile AOI and clip the composite
            tile_aoi = self.gee.build_aoi_from_bbox(*tile.bbox)
            clipped = composite.clip(tile_aoi)

            # Export GeoTIFF
            dest_path = self._cfg.tile_file_path(lake_id, year, tile.tile_index)
            log.info("Exporting tile GeoTIFF", dest=str(dest_path))

            self.gee.export_geotiff(
                clipped,
                tile_aoi,
                dest_path,
                max_retries=self._cfg.max_retries,
                retry_delay=self._cfg.retry_delay_sec,
                retry_backoff=self._cfg.retry_backoff,
                timeout_sec=self._cfg.download_timeout_sec,
            )

            # Update metadata
            file_size = dest_path.stat().st_size
            rel_path = str(
                dest_path.relative_to(self._cfg.data_root.parent.parent)
            )
            self._upsert_tile_status(
                lake_id,
                year,
                tile.tile_index,
                "COMPLETED",
                image_path=rel_path,
                file_size_bytes=file_size,
            )

            log.info(
                "✓ Tile download completed",
                file_size=file_size,
            )
            return "completed"

        except Exception as exc:
            error_msg = str(exc)[:500]
            log.error("✗ Tile download failed", error=error_msg)
            self._upsert_tile_status(
                lake_id,
                year,
                tile.tile_index,
                "FAILED",
                error_message=error_msg,
                increment_retry=True,
            )
            return "failed"

    # ── Single-lake Drive pipeline ────────────────────────────────────────

    def download_lake_drive(
        self,
        lake_id: int,
        year: int,
        *,
        cancel_check: Optional[Callable] = None,
    ) -> str:
        """
        Full Drive-export pipeline for one lake / one year.

        Pipeline:
          1. Read lake polygon from PostGIS.
          2. Buffer in projected CRS.
          3. Build Sentinel-2 composite via Earth Engine.
          4. ``Export.image.toDrive()`` (no tile grid, no local download).
          5. Wait until the export completes.
          6. Upsert ``lake_images`` with a ``drive://`` path.

        Args:
            lake_id: The HydroLAKES lake ID.
            year: The target year.
            cancel_check: Returns ``True`` to abort.

        Returns:
            ``"completed"`` or ``"failed"``.
        """
        log = logger.bind(lake_id=lake_id, year=year, mode="drive")

        try:
            # 1. Read lake polygon
            log.info("Step 1: Reading lake polygon from PostGIS")
            geom_4326 = self._read_lake_polygon(lake_id)
            if geom_4326 is None:
                raise ValueError(f"Lake {lake_id} has no geometry in PostGIS")

            if cancel_check and cancel_check():
                return "failed"

            # 2. Buffer
            log.info(
                "Step 2: Projecting → buffering → reprojecting",
                buffer_m=self._cfg.buffer_distance_m,
            )
            buffered_geom = self._buffer_polygon(geom_4326)

            # 3. Build composite over the full buffered extent
            full_bbox = buffered_geom.bounds  # (minx, miny, maxx, maxy)
            log.info(
                "Step 3: Building Sentinel-2 composite via GEE",
                west=full_bbox[0],
                south=full_bbox[1],
                east=full_bbox[2],
                north=full_bbox[3],
            )
            full_aoi = self.gee.build_aoi_from_bbox(*full_bbox)
            composite = self.gee.build_composite(full_aoi, year)

            if cancel_check and cancel_check():
                return "failed"

            # 4. Mark as DOWNLOADING
            drive_path = (
                f"drive://{self._cfg.drive_folder}/{year}/lake_{lake_id:06d}"
            )
            self._upsert_lake_image_status(
                lake_id,
                year,
                "downloading",
                file_path=drive_path,
            )

            # 5. Export to Drive and wait
            log.info(
                "Step 4-5: Exporting to Google Drive and waiting",
                folder=self._cfg.drive_folder,
            )
            result = self.gee.export_full_lake_to_drive(
                composite=composite,
                aoi=full_aoi,
                lake_id=lake_id,
                year=year,
            )

            # 6. Update lake_images → COMPLETED
            self._upsert_lake_image_status(
                lake_id,
                year,
                "completed",
                file_path=drive_path,
            )

            log.info(
                "✓ Drive export completed",
                drive_path=drive_path,
                task_id=result.get("task_id"),
            )
            return "completed"

        except Exception as exc:
            error_msg = str(exc)[:500]
            log.error("✗ Drive export failed", error=error_msg)
            self._upsert_lake_image_status(
                lake_id,
                year,
                "failed",
                error_message=error_msg,
            )
            return "failed"

    # ── Batch pipeline ────────────────────────────────────────────────────

    def download_batch(
        self,
        lake_ids: List[int],
        years: List[int],
        *,
        cancel_check: Optional[Callable] = None,
        tile_callback: Optional[Callable] = None,
        lake_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Download imagery for multiple lakes × years using tile-based grid.

        Args:
            lake_ids: List of lake IDs.
            years: List of years.
            cancel_check: Callable that returns True to abort.
            tile_callback: Called after each tile with
                ``(lake_id, year, tile_index, result)``.
            lake_callback: Called after each lake/year with
                ``(lake_id, year, result)``.

        Returns:
            Summary dict with success/failed/skipped counts (lake-level).
        """
        total = len(lake_ids) * len(years)
        success = 0
        failed = 0
        skipped = 0

        logger.info(
            "Batch download started",
            total_lakes=len(lake_ids),
            total_years=len(years),
            total_tasks=total,
        )

        for lake_id in lake_ids:
            for year in years:
                if cancel_check and cancel_check():
                    logger.warning("Batch download cancelled by user")
                    return {
                        "success": success,
                        "failed": failed,
                        "skipped": skipped,
                        "cancelled": True,
                    }

                result = self.download_lake(
                    lake_id,
                    year,
                    cancel_check=cancel_check,
                    tile_callback=tile_callback,
                )

                if result == "completed":
                    success += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1

                if lake_callback:
                    lake_callback(lake_id, year, result)

        logger.info(
            "Batch download finished",
            success=success,
            failed=failed,
            skipped=skipped,
        )
        return {
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "cancelled": False,
        }

    # ── PostGIS helpers ───────────────────────────────────────────────────

    def _read_lake_polygon(self, lake_id: int):
        """Read the lake polygon as a Shapely geometry (EPSG:4326)."""
        with self._Session() as session:
            lake = session.execute(
                select(Lake).where(Lake.lake_id == lake_id)
            ).scalar_one_or_none()

            if lake is None or lake.geom is None:
                return None
            return to_shape(lake.geom)

    def _buffer_polygon(self, geom_4326):
        """
        Buffer the polygon in a projected CRS and convert back to 4326.

        Steps:
          1. EPSG:4326 → projected CRS (6933 = equal-area cylindrical)
          2. Buffer by configured distance
          3. Projected CRS → EPSG:4326
        """
        proj_crs = self._cfg.projected_crs

        # Forward transform: 4326 → projected
        to_projected = Transformer.from_crs(
            4326, proj_crs, always_xy=True
        ).transform
        projected_geom = transform(to_projected, geom_4326)

        # Buffer in projected CRS (metres)
        buffered = projected_geom.buffer(self._cfg.buffer_distance_m)

        # Inverse transform: projected → 4326
        to_4326 = Transformer.from_crs(
            proj_crs, 4326, always_xy=True
        ).transform
        return transform(to_4326, buffered)

    # ── Tile metadata helpers ─────────────────────────────────────────────

    def _ensure_tile_rows(
        self,
        lake_id: int,
        year: int,
        tiles: List[TileInfo],
    ) -> None:
        """Insert PENDING rows for tiles that don't yet exist in lake_tiles."""
        from geoalchemy2.shape import from_shape

        now = datetime.now(timezone.utc)
        with self._Session() as session:
            for tile in tiles:
                stmt = pg_insert(LakeTile).values(
                    lake_id=lake_id,
                    year=year,
                    tile_index=tile.tile_index,
                    tile_geometry=from_shape(tile.geometry_4326, srid=4326),
                    bbox=f"{tile.bbox[0]},{tile.bbox[1]},{tile.bbox[2]},{tile.bbox[3]}",
                    status="PENDING",
                    image_path=str(
                        self._cfg.tile_file_path(
                            lake_id, year, tile.tile_index
                        ).relative_to(self._cfg.data_root.parent.parent)
                    ),
                    created_at=now,
                    updated_at=now,
                )
                # Don't overwrite completed tiles
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_lake_tiles_lake_year_tile"
                )
                session.execute(stmt)
            session.commit()

    def _get_pending_tile_indices(
        self, lake_id: int, year: int
    ) -> set:
        """Return tile_index values not yet COMPLETED (or whose file is missing)."""
        with self._Session() as session:
            rows = (
                session.execute(
                    select(LakeTile.tile_index, LakeTile.status, LakeTile.image_path)
                    .where(
                        LakeTile.lake_id == lake_id,
                        LakeTile.year == year,
                    )
                )
                .all()
            )

        pending = set()
        for tile_index, status, image_path in rows:
            if status != "COMPLETED":
                pending.add(tile_index)
            elif image_path:
                # Verify file still exists on disk
                full_path = self._cfg.data_root.parent.parent / image_path
                if not full_path.is_file():
                    pending.add(tile_index)

        return pending

    def _upsert_tile_status(
        self,
        lake_id: int,
        year: int,
        tile_index: str,
        status: str,
        *,
        image_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        error_message: Optional[str] = None,
        increment_retry: bool = False,
    ) -> None:
        """Insert or update a lake_tiles metadata row."""
        now = datetime.now(timezone.utc)

        with self._Session() as session:
            stmt = pg_insert(LakeTile).values(
                lake_id=lake_id,
                year=year,
                tile_index=tile_index,
                status=status,
                image_path=image_path or "",
                file_size_bytes=file_size_bytes,
                error_message=error_message,
                retry_count=1 if increment_retry else 0,
                created_at=now,
                updated_at=now,
            )

            update_dict: Dict = {
                "status": status,
                "updated_at": now,
            }
            if image_path is not None:
                update_dict["image_path"] = image_path
            if file_size_bytes is not None:
                update_dict["file_size_bytes"] = file_size_bytes
            if error_message is not None:
                update_dict["error_message"] = error_message
            elif status == "COMPLETED":
                update_dict["error_message"] = None
            if increment_retry:
                update_dict["retry_count"] = LakeTile.retry_count + 1

            stmt = stmt.on_conflict_do_update(
                constraint="uq_lake_tiles_lake_year_tile",
                set_=update_dict,
            )
            session.execute(stmt)
            session.commit()

    # ── Lake-level metadata helpers ───────────────────────────────────────

    def _update_lake_image_aggregate(
        self, lake_id: int, year: int
    ) -> None:
        """
        Update the parent lake_images row based on aggregate tile statuses.

        - All tiles COMPLETED → lake_images status = "completed"
        - Any tile FAILED → lake_images status = "failed"
        - Otherwise → lake_images status = "downloading"
        """
        with self._Session() as session:
            rows = (
                session.execute(
                    select(LakeTile.status)
                    .where(
                        LakeTile.lake_id == lake_id,
                        LakeTile.year == year,
                    )
                )
                .scalars()
                .all()
            )

        if not rows:
            return

        statuses = set(rows)
        total_size = 0

        if statuses == {"COMPLETED"}:
            # Sum up file sizes
            with self._Session() as session:
                total_size = (
                    session.execute(
                        select(func.sum(LakeTile.file_size_bytes)).where(
                            LakeTile.lake_id == lake_id,
                            LakeTile.year == year,
                        )
                    )
                    .scalar()
                    or 0
                )
            agg_status = "completed"
        elif "FAILED" in statuses:
            agg_status = "failed"
        else:
            agg_status = "downloading"

        # Build the tile directory as the "file_path" for the lake image
        tile_dir = str(
            self._cfg.lake_tile_dir(lake_id, year).relative_to(
                self._cfg.data_root.parent.parent
            )
        )

        self._upsert_lake_image_status(
            lake_id,
            year,
            agg_status,
            file_path=tile_dir,
            file_size_bytes=total_size if agg_status == "completed" else None,
        )

    def _upsert_lake_image_status(
        self,
        lake_id: int,
        year: int,
        status: str,
        *,
        file_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        error_message: Optional[str] = None,
        increment_retry: bool = False,
    ) -> None:
        """Insert or update the lake_images metadata row."""
        now = datetime.now(timezone.utc)
        default_path = str(
            self._cfg.lake_tile_dir(lake_id, year).relative_to(
                self._cfg.data_root.parent.parent
            )
        )

        with self._Session() as session:
            stmt = pg_insert(LakeImage).values(
                lake_id=lake_id,
                year=year,
                file_path=file_path or default_path,
                status=status,
                file_size_bytes=file_size_bytes,
                error_message=error_message,
                retry_count=1 if increment_retry else 0,
                created_at=now,
                updated_at=now,
            )

            update_dict: Dict = {
                "status": status,
                "updated_at": now,
            }
            if file_path is not None:
                update_dict["file_path"] = file_path
            if file_size_bytes is not None:
                update_dict["file_size_bytes"] = file_size_bytes
            if error_message is not None:
                update_dict["error_message"] = error_message
            elif status == "completed":
                update_dict["error_message"] = None
            if increment_retry:
                update_dict["retry_count"] = LakeImage.retry_count + 1

            stmt = stmt.on_conflict_do_update(
                constraint="uq_lake_images_lake_year",
                set_=update_dict,
            )
            session.execute(stmt)
            session.commit()

    def get_active_lake_ids(self) -> List[int]:
        """Return all active lake IDs from the database."""
        with self._Session() as session:
            rows = session.execute(
                select(Lake.lake_id).where(Lake.is_active.is_(True))
            ).scalars().all()
            return list(rows)
