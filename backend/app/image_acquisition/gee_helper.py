"""
Google Earth Engine helper for per-lake Sentinel-2 composite downloads.

Provides a clean interface for:
  - Building composites from Sentinel-2 Surface Reflectance imagery
  - SCL-based cloud/shadow masking
  - Selecting Prithvi-compatible bands
  - Exporting clipped GeoTIFF files

All GEE operations are encapsulated here so the downloader module
never imports ``ee`` directly.
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.ML_pipeline.constants import (
    GEE_CLOUD_COVER_MAX,
    GEE_SCALE_METRES,
    GEE_SENTINEL2_COLLECTION,
    S2_BANDS_PRITHVI,
)
from app.image_acquisition.config import ImageAcquisitionConfig

logger = structlog.get_logger(__name__)


def _require_ee():
    """Import and initialize the Earth Engine client."""
    try:
        import ee  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "earthengine-api is not installed. "
            "Run: pip install earthengine-api  then  earthengine authenticate"
        ) from exc

    from app.ML_pipeline.gee_init import ensure_gee_initialized  # noqa: PLC0415

    ensure_gee_initialized()
    return ee


class SentinelCompositeBuilder:
    """Builds and exports Sentinel-2 annual composites via Earth Engine."""

    def __init__(self, config: ImageAcquisitionConfig) -> None:
        self._cfg = config
        self._ee = _require_ee()

    # ── AOI construction ──────────────────────────────────────────────────

    def build_aoi_from_geojson(self, geojson_geom: Dict[str, Any]) -> Any:
        """Convert a GeoJSON geometry dict to an ``ee.Geometry``."""
        return self._ee.Geometry(geojson_geom)

    def build_aoi_from_bbox(
        self, west: float, south: float, east: float, north: float
    ) -> Any:
        """Build an ``ee.Geometry.BBox`` from bounding-box coordinates."""
        return self._ee.Geometry.BBox(west, south, east, north)

    # ── Cloud masking ─────────────────────────────────────────────────────

    def _cloud_mask_scl(self, image: Any) -> Any:
        """
        Mask clouds, shadows, and snow using the Sentinel-2 SCL band.

        SCL values to mask:
          3 = Cloud Shadow
          7 = Unclassified (often thin cloud)
          8 = Cloud medium probability
          9 = Cloud high probability
         10 = Thin cirrus
         11 = Snow / Ice
        """
        scl = image.select("SCL")
        mask = (
            scl.neq(3)
            .And(scl.neq(7))
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10))
            .And(scl.neq(11))
        )
        return image.updateMask(mask)

    # ── Composite construction ────────────────────────────────────────────

    def build_composite(self, aoi: Any, year: int) -> Any:
        """
        Build a yearly median composite from Sentinel-2 SR for the given AOI.

        Steps:
          1. Filter collection by AOI, date range, and cloud cover percentage.
          2. Apply SCL-based cloud masking to each image.
          3. Compute median composite.
          4. Select Prithvi bands (B2–B7).
          5. Clip to AOI.
        """
        ee = self._ee
        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"

        collection = (
            ee.ImageCollection(self._cfg.sentinel_collection)
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(
                ee.Filter.lt(
                    "CLOUDY_PIXEL_PERCENTAGE",
                    self._cfg.cloud_cover_max,
                )
            )
            .map(self._cloud_mask_scl)
        )

        # Yearly median composite
        composite_method = self._cfg.composite_method
        if composite_method == "median":
            composite = collection.median()
        elif composite_method == "mean":
            composite = collection.mean()
        else:
            composite = collection.mosaic()

        # Select Prithvi bands and clip to AOI
        composite = composite.select(list(self._cfg.prithvi_bands)).clip(aoi)
        return composite

    # ── GeoTIFF export ────────────────────────────────────────────────────

    def export_geotiff(
        self,
        composite: Any,
        aoi: Any,
        dest_path: Path,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        retry_backoff: float = 2.0,
        timeout_sec: int = 600,
    ) -> Path:
        """
        Download the composite as a GeoTIFF to ``dest_path``.

        Uses ``ee.Image.getDownloadURL`` to stream the image as a
        single-file GeoTIFF.  Retries on transient / quota errors.
        """
        ee = self._ee
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        download_params = {
            "bands": list(self._cfg.prithvi_bands),
            "region": aoi,
            "scale": self._cfg.scale_metres,
            "crs": self._cfg.output_crs,
            "filePerBand": False,
            "format": "GEO_TIFF",
        }

        delay = retry_delay
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                url = composite.getDownloadURL(download_params)
                logger.info(
                    "GeoTIFF download started",
                    attempt=attempt,
                    dest=str(dest_path),
                )

                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    with open(dest_path, "wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)

                logger.info(
                    "GeoTIFF download completed",
                    dest=str(dest_path),
                    size_bytes=dest_path.stat().st_size,
                )
                return dest_path

            except Exception as exc:
                last_error = exc
                error_str = str(exc).lower()

                # Check for quota / rate-limit errors
                is_quota = any(
                    kw in error_str
                    for kw in ("quota", "rate limit", "429", "too many")
                )

                if attempt < max_retries:
                    wait = delay * (2 if is_quota else 1)
                    logger.warning(
                        "GeoTIFF download failed — retrying",
                        attempt=attempt,
                        error=str(exc),
                        retry_in_sec=wait,
                        is_quota_error=is_quota,
                    )
                    time.sleep(wait)
                    delay *= retry_backoff
                else:
                    logger.error(
                        "GeoTIFF download failed — retries exhausted",
                        attempt=attempt,
                        error=str(exc),
                    )

        raise RuntimeError(
            f"GeoTIFF download failed after {max_retries} attempts: {last_error}"
        )
