"""
Image acquisition configuration.

Centralises all tuneable values for the per-lake Sentinel-2 download pipeline,
including the tile-based grid partitioning for large lakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from app.ML_pipeline.constants import (
    GEE_CLOUD_COVER_MAX,
    GEE_COMPOSITE_METHOD,
    GEE_SCALE_METRES,
    GEE_SENTINEL2_COLLECTION,
    S2_BANDS_DOWNLOAD,
)
from app.core.config import settings
from app.image_acquisition.storage import (
    default_data_root,
    resolve_stored_path,
    to_stored_path,
)


class AcquisitionMode(str, Enum):
    """Supported image-acquisition strategies."""

    TILE = "tile"
    DRIVE = "drive"


@dataclass(frozen=True)
class ImageAcquisitionConfig:
    """Runtime configuration for lake-level Sentinel-2 downloads.

    ``data_root`` is the default storage root (``SENTINEL_DATA_DIR``);
    ``year_roots`` holds the roots chosen for a download run (see
    ``storage.py``). Always use :meth:`root_for_year`.
    """

    data_root: Path
    buffer_distance_m: int
    projected_crs: int
    output_crs: str
    scale_metres: int
    cloud_cover_max: int
    composite_method: str
    sentinel_collection: str
    download_bands: tuple[str, ...]
    max_retries: int
    retry_delay_sec: float
    retry_backoff: float
    download_timeout_sec: int
    batch_size: int
    tile_size_m: int
    download_workers: int
    lake_workers: int
    mode: AcquisitionMode
    drive_folder: str
    drive_poll_interval_sec: int
    drive_timeout_min: int
    year_roots: dict = field(default_factory=dict)

    def root_for_year(self, year: int) -> Path:
        """Storage root that year ``year`` is written to."""
        return self.year_roots.get(int(year), self.data_root)

    # ── Lake-level paths (legacy — retained for backward compat) ──────────

    def lake_file_path(self, lake_id: int, year: int) -> Path:
        """Return the canonical on-disk path for a lake/year GeoTIFF."""
        return self.root_for_year(year) / str(year) / f"lake_{lake_id:06d}.tif"

    # ── Tile-level paths ──────────────────────────────────────────────────

    def lake_tile_dir(self, lake_id: int, year: int) -> Path:
        """Return the directory for a lake's tile GeoTIFFs."""
        return self.root_for_year(year) / str(year) / f"lake_{lake_id:06d}"

    def tile_file_path(self, lake_id: int, year: int, tile_index: str) -> Path:
        """Return the canonical path for a single tile GeoTIFF."""
        return self.lake_tile_dir(lake_id, year) / f"tile_{tile_index}.tif"

    def resolve_path(self, stored_path: str) -> Path:
        """Absolute path for a ``file_path`` / ``image_path`` stored in the DB."""
        return resolve_stored_path(stored_path)

    def stored_path(self, path: Path) -> str:
        """DB form of ``path`` (backend-relative if inside the backend folder)."""
        return to_stored_path(path)

    def ensure_year_dirs(self, years) -> None:
        """Create ``<root>/<year>`` for every year about to be downloaded."""
        for year in years:
            (self.root_for_year(year) / str(year)).mkdir(parents=True, exist_ok=True)


def get_image_acquisition_config(
    year_roots: Optional[Dict[int, Path]] = None,
) -> ImageAcquisitionConfig:
    """Build the config. ``year_roots`` maps years to the storage root new
    files are written to; years not in it use ``SENTINEL_DATA_DIR``."""
    return ImageAcquisitionConfig(
        data_root=default_data_root(),
        year_roots=dict(year_roots or {}),
        buffer_distance_m=settings.LAKE_IMAGERY_BUFFER_METRES,
        projected_crs=6933,
        output_crs="EPSG:4326",
        scale_metres=GEE_SCALE_METRES,
        cloud_cover_max=GEE_CLOUD_COVER_MAX,
        composite_method=GEE_COMPOSITE_METHOD,
        sentinel_collection=GEE_SENTINEL2_COLLECTION,
        download_bands=tuple(S2_BANDS_DOWNLOAD),
        max_retries=settings.IMAGERY_MAX_RETRIES,
        retry_delay_sec=settings.IMAGERY_RETRY_DELAY_SEC,
        retry_backoff=settings.IMAGERY_RETRY_BACKOFF,
        download_timeout_sec=settings.IMAGERY_DOWNLOAD_TIMEOUT_SEC,
        batch_size=settings.IMAGERY_BATCH_SIZE,
        tile_size_m=settings.IMAGERY_TILE_SIZE_METRES,
        download_workers=settings.IMAGERY_DOWNLOAD_WORKERS,
        lake_workers=settings.IMAGERY_LAKE_WORKERS,
        mode=AcquisitionMode(settings.IMAGE_ACQUISITION_MODE),
        drive_folder=settings.GEE_DRIVE_FOLDER,
        drive_poll_interval_sec=settings.GEE_DRIVE_POLL_INTERVAL_SEC,
        drive_timeout_min=settings.GEE_DRIVE_TIMEOUT_MIN,
    )
