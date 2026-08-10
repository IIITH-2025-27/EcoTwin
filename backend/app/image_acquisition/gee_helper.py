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
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
import datetime

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

    @property
    def ee_module(self) -> Any:
        """The initialized ``ee`` module, for callers that need direct GEE API access
        (e.g. server-side reducers) beyond what this class wraps."""
        return self._ee

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

    def build_composite(
        self, aoi: Any, year: int, bands: Optional[Sequence[str]] = None
    ) -> Any:
        """
        Build a yearly median composite from Sentinel-2 SR for the given AOI.

        Steps:
          1. Filter collection by AOI, date range, and cloud cover percentage.
          2. Apply SCL-based cloud masking to each image.
          3. Compute median composite.
          4. Select bands (defaults to the Prithvi bands, B2–B7; pass an
             explicit ``bands`` list, e.g. ``["B8"]``, for other fetches —
             this never mutates ``self._cfg.prithvi_bands``).
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

        # Select requested bands (default: Prithvi bands) and clip to AOI
        select_bands = list(bands) if bands is not None else list(self._cfg.prithvi_bands)
        composite = composite.select(select_bands).clip(aoi)
        return composite

    # ── GeoTIFF export ────────────────────────────────────────────────────

    def export_geotiff(
        self,
        composite: Any,
        aoi: Any,
        dest_path: Path,
        bands: Optional[Sequence[str]] = None,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        retry_backoff: float = 2.0,
        timeout_sec: int = 600,
    ) -> Path:
        """
        Download the composite as a GeoTIFF to ``dest_path``.

        Uses ``ee.Image.getDownloadURL`` to stream the image as a
        single-file GeoTIFF.  Retries on transient / quota errors.

        ``bands`` defaults to the Prithvi bands; pass the same band list
        used in the matching ``build_composite()`` call (e.g. ``["B8"]``)
        for other fetches.
        """
        ee = self._ee
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        download_params = {
            "bands": list(bands) if bands is not None else list(self._cfg.prithvi_bands),
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

            except urllib.error.HTTPError as exc:
                last_error = exc
            
                try:
                    body = exc.read().decode("utf-8", errors="ignore")
                except Exception:
                    body = "<unable to read response body>"
            
                logger.error(
                    "Earth Engine HTTP Error",
                    attempt=attempt,
                    status=exc.code,
                    reason=exc.reason,
                    response=body,
                )
            
                # Don't retry invalid requests
                if exc.code == 400:
                    raise RuntimeError(
                        f"Earth Engine rejected the request (HTTP 400): {body}"
                    ) from exc
            
                error_str = body.lower()
            
                is_quota = any(
                    kw in error_str
                    for kw in ("quota", "rate limit", "429", "too many")
                )
            
                if attempt < max_retries:
                    wait = delay * (2 if is_quota else 1)
            
                    logger.warning(
                        "GeoTIFF download failed — retrying",
                        attempt=attempt,
                        retry_in_sec=wait,
                        is_quota_error=is_quota,
                    )
            
                    time.sleep(wait)
                    delay *= retry_backoff
                else:
                    logger.error(
                        "GeoTIFF download failed — retries exhausted",
                        attempt=attempt,
                        status=exc.code,
                    )
            
            except Exception as exc:
                last_error = exc
                error_str = str(exc).lower()
            
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

    # ──────────────────────────────────────────────────────────────────────────────
    # Google Drive Export
    # ──────────────────────────────────────────────────────────────────────────────

    def export_to_drive(
        self,
        composite: Any,
        aoi: Any,
        lake_id: int,
        year: int,
        folder: str,
        scale: int | None = None,
    ):
        """
        Export the full buffered lake composite to Google Drive.

        Returns
        -------
        ee.batch.Task
            Running Earth Engine export task.
        """

        ee = self._ee

        if scale is None:
            scale = self._cfg.scale_metres

        description = f"lake_{lake_id:06d}_{year}"
        file_prefix = f"lake_{lake_id:06d}"

        task = ee.batch.Export.image.toDrive(
            image=composite,
            description=description,
            folder=folder,
            fileNamePrefix=file_prefix,
            region=aoi,
            scale=scale,
            crs=self._cfg.output_crs,
            maxPixels=1e13,
            fileFormat="GeoTIFF",
            formatOptions={
                "cloudOptimized": True
            },
        )

        task.start()

        logger.info(
            "Started Google Drive export",
            lake_id=lake_id,
            year=year,
            folder=folder,
            description=description,
            task_id=task.id,
        )

        return task
    
    def wait_for_drive_export(
        self,
        task,
        poll_interval_sec: int = 20,
        timeout_minutes: int = 180,
    ):  
        """
        Wait until an Earth Engine Drive export completes.

        Raises
        ------
        RuntimeError
            If export fails, is cancelled, or times out.
        """

        deadline = (
            datetime.datetime.utcnow()
            + datetime.timedelta(minutes=timeout_minutes)
        )

        logger.info(
            "Waiting for Google Drive export",
            task_id=task.id,
        )

        while True:

            status = task.status()

            state = status.get("state")

            if state == "COMPLETED":

                logger.info(
                    "Drive export completed",
                    task_id=task.id,
                )

                return status

            if state == "FAILED":

                raise RuntimeError(
                    f"Drive export failed: "
                    f"{status.get('error_message', 'Unknown error')}"
                )

            if state == "CANCELLED":

                raise RuntimeError(
                    "Drive export cancelled."
                )

            if datetime.datetime.utcnow() > deadline:

                try:
                    task.cancel()
                except Exception:
                    pass

                raise TimeoutError(
                    f"Drive export timed out after "
                    f"{timeout_minutes} minutes."
                )

            logger.info(
                "Drive export running",
                task_id=task.id,
                state=state,
            )

            time.sleep(poll_interval_sec)
    def cancel_drive_export(self, task):
        """
        Cancel a running Earth Engine Drive export.
        """

        try:
            task.cancel()

            logger.info(
                "Drive export cancelled",
                task_id=task.id,
            )

        except Exception as exc:

            logger.warning(
                "Unable to cancel Drive export",
                task_id=task.id,
                error=str(exc),
            )
        
    def export_full_lake_to_drive(
        self,
        composite: Any,
        aoi: Any,
        lake_id: int,
        year: int,
    ):
        """
        Convenience wrapper.

        Starts a Drive export and blocks until it finishes.
        """

        task = self.export_to_drive(
            composite=composite,
            aoi=aoi,
            lake_id=lake_id,
            year=year,
            folder=self._cfg.drive_folder,
            scale=self._cfg.scale_metres,
        )

        self.wait_for_drive_export(
            task,
            poll_interval_sec=self._cfg.drive_poll_interval_sec,
            timeout_minutes=self._cfg.drive_timeout_min,
        )

        return {
            "status": "completed",
            "task_id": task.id,
            "drive_folder": self._cfg.drive_folder,
            "filename": f"lake_{lake_id:06d}.tif",
        }
# start_drive_export()
