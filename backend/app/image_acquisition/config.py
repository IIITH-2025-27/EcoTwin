"""
Image acquisition configuration.

Centralises all tuneable values for the per-lake Sentinel-2 download pipeline,
including the tile-based grid partitioning for large lakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.ML_pipeline.constants import (
    GEE_CLOUD_COVER_MAX,
    GEE_COMPOSITE_METHOD,
    GEE_SCALE_METRES,
    GEE_SENTINEL2_COLLECTION,
    S2_BANDS_PRITHVI,
)
from app.core.config import settings


class AcquisitionMode(str, Enum):
    """Supported image-acquisition strategies."""

    TILE = "tile"
    DRIVE = "drive"


@dataclass(frozen=True)
class ImageAcquisitionConfig:
    """Runtime configuration for lake-level Sentinel-2 downloads."""

    data_root: Path
    buffer_distance_m: int
    projected_crs: int
    output_crs: str
    scale_metres: int
    cloud_cover_max: int
    composite_method: str
    sentinel_collection: str
    prithvi_bands: tuple[str, ...]
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

    # ── Lake-level paths (legacy — retained for backward compat) ──────────

    def lake_file_path(self, lake_id: int, year: int) -> Path:
        """Return the canonical on-disk path for a lake/year GeoTIFF."""
        return self.data_root / str(year) / f"lake_{lake_id:06d}.tif"

    # ── Tile-level paths ──────────────────────────────────────────────────

    def lake_tile_dir(self, lake_id: int, year: int) -> Path:
        """Return the directory for a lake's tile GeoTIFFs."""
        return self.data_root / str(year) / f"lake_{lake_id:06d}"

    def tile_file_path(self, lake_id: int, year: int, tile_index: str) -> Path:
        """Return the canonical path for a single tile GeoTIFF."""
        return self.lake_tile_dir(lake_id, year) / f"tile_{tile_index}.tif"

    def ensure_data_root(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)


def get_image_acquisition_config() -> ImageAcquisitionConfig:
    backend_root = Path(__file__).resolve().parents[2]
    data_root = Path(settings.SENTINEL_DATA_DIR)
    if not data_root.is_absolute():
        data_root = backend_root / data_root

    return ImageAcquisitionConfig(
        data_root=data_root,
        buffer_distance_m=settings.LAKE_IMAGERY_BUFFER_METRES,
        projected_crs=6933,
        output_crs="EPSG:4326",
        scale_metres=GEE_SCALE_METRES,
        cloud_cover_max=GEE_CLOUD_COVER_MAX,
        composite_method=GEE_COMPOSITE_METHOD,
        sentinel_collection=GEE_SENTINEL2_COLLECTION,
        prithvi_bands=tuple(S2_BANDS_PRITHVI),
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
