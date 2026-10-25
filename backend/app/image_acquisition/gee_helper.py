"""
Google Earth Engine helper for per-lake Sentinel-2 composite downloads.

Provides a clean interface for:
  - Building composites from Sentinel-2 Surface Reflectance imagery
  - Cloud Score+ cloud/haze/shadow masking (plus SCL saturation/snow)
  - Selecting the full download band stack (S2_BANDS_DOWNLOAD)
  - Exporting clipped GeoTIFF files

All GEE operations are encapsulated here so the downloader module
never imports ``ee`` directly.
"""

from __future__ import annotations

import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple
import datetime

import structlog

from app.ML_pipeline.constants import (
    GEE_CLOUD_COVER_MAX,
    GEE_CLOUD_SCORE_BAND,
    GEE_CLOUD_SCORE_COLLECTION,
    GEE_CLOUD_SCORE_MIN,
    GEE_CRS_TRANSFORM,
    GEE_SCALE_METRES,
    GEE_SENTINEL2_COLLECTION,
    S2_BAND_CLEAR_COUNT,
    S2_BANDS_DOWNLOAD,
    S2_NODATA,
)
from app.image_acquisition.config import ImageAcquisitionConfig
from app.image_acquisition.merger import mosaic_geotiffs, set_nodata_tag
from app.ML_pipeline.gee_init import (
    current_gee_account,
    gee_account_count,
    rotate_gee_account,
)

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


# Errors that mean "this account cannot be used right now" (quota, rate
# limit, invalid / unregistered key) rather than "this request is bad".
_ACCOUNT_ERROR_MARKERS = (
    "429", "too many requests", "quota", "rate limit", "capacity exceeded",
    "too many concurrent", "invalid_grant", "not registered", "permission_denied",
)


def _is_account_error(text: str) -> bool:
    text = text.lower()
    return any(marker in text for marker in _ACCOUNT_ERROR_MARKERS)


class EarthEngineMemoryError(RuntimeError):
    """Earth Engine refused a download with "User memory limit exceeded"
    (the request is too heavy; retrying the same request will not help)."""


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

    def _mask_image(self, image: Any) -> Any:
        """
        Mask one Sentinel-2 SR scene before compositing.

        Cloud Score+ (``cs_cdf`` linked in by ``build_composite``) removes
        cloud, haze, and cloud shadow: pixels with a clear-sky score below
        ``GEE_CLOUD_SCORE_MIN`` are masked. SCL is still used for what
        Cloud Score+ does not flag:
          1 = Saturated / defective
         11 = Snow / Ice
        """
        clear = image.select(GEE_CLOUD_SCORE_BAND).gte(GEE_CLOUD_SCORE_MIN)
        scl = image.select("SCL")
        mask = clear.And(scl.neq(1)).And(scl.neq(11))
        return image.updateMask(mask)

    # ── Composite construction ────────────────────────────────────────────

    def build_composite(
        self, aoi: Any, year: int, bands: Optional[Sequence[str]] = None
    ) -> Any:
        """
        Build a yearly median composite from Sentinel-2 SR for the given AOI.

        Steps:
          1. Filter collection by AOI, date range, and cloud cover percentage.
          2. Link Cloud Score+ and mask each scene (``_mask_image``).
          3. Compute median composite.
          4. Select bands (defaults to the full download stack,
             ``S2_BANDS_DOWNLOAD``; pass an explicit ``bands`` list, e.g.
             ``["B8"]``, for other fetches), round, and cast to uint16.
             ``CLEAR_COUNT``, if requested, is the per-pixel number of
             unmasked scenes that went into the median.
          5. Clip to AOI.

        The rounded uint16 cast loses nothing meaningful (S2 SR is integer
        reflectance × 10000) and keeps tiles 4× smaller than the float64 a
        median composite would otherwise produce.

        Masked pixels stay masked here so server-side reducers ignore them;
        the export methods fill them with ``S2_NODATA``.
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
            .linkCollection(
                ee.ImageCollection(GEE_CLOUD_SCORE_COLLECTION),
                [GEE_CLOUD_SCORE_BAND],
            )
            .map(self._mask_image)
        )

        # Yearly median composite
        composite_method = self._cfg.composite_method
        if composite_method == "median":
            composite = collection.median()
        elif composite_method == "mean":
            composite = collection.mean()
        else:
            composite = collection.mosaic()

        # Select requested bands (default: full download stack) and clip to AOI
        select_bands = list(bands) if bands is not None else list(self._cfg.download_bands)
        spectral = [b for b in select_bands if b != S2_BAND_CLEAR_COUNT]
        composite = composite.select(spectral)
        if S2_BAND_CLEAR_COUNT in select_bands:
            clear_count = (
                collection.select(spectral[0]).count().rename(S2_BAND_CLEAR_COUNT)
            )
            composite = composite.addBands(clear_count)
        composite = composite.select(select_bands).round().toUint16().clip(aoi)
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

        ``bands`` defaults to the full download stack; pass the same band list
        used in the matching ``build_composite()`` call (e.g. ``["B8"]``)
        for other fetches.

        Masked pixels (clouds, outside the AOI) are written as ``S2_NODATA``.
        """
        ee = self._ee
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        composite = composite.unmask(S2_NODATA, False)

        download_params = {
            "bands": list(bands) if bands is not None else list(self._cfg.download_bands),
            "region": aoi,
            # Fixed global grid (GEE_SCALE_METRES) instead of "scale", so
            # tiles and years share pixel boundaries.
            "crs_transform": list(GEE_CRS_TRANSFORM),
            "crs": self._cfg.output_crs,
            "filePerBand": False,
            "format": "GEO_TIFF",
        }

        delay = retry_delay
        last_error: Optional[Exception] = None
        attempt = 0
        switches = 0

        while attempt < max_retries:
            attempt += 1
            account = current_gee_account()
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

                # GEE tags downloads nodata=0; the fill value is S2_NODATA
                set_nodata_tag(dest_path)
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
                if exc.code == 400 and "memory limit" in body.lower():
                    raise EarthEngineMemoryError(
                        f"Earth Engine rejected the request (HTTP 400): {body}"
                    ) from exc
                error_text = f"HTTP {exc.code} {exc.reason} {body}"
                retryable = exc.code != 400

            except Exception as exc:
                last_error = exc
                error_text = str(exc)
                retryable = True

            # Account-level rejection (quota, rate limit, bad key): switch to
            # the next service account and retry without using up an attempt.
            if _is_account_error(error_text) and switches < max(1, gee_account_count()):
                if rotate_gee_account(account, error_text):
                    switches += 1
                    attempt -= 1
                    continue

            if not retryable:
                raise RuntimeError(
                    f"Earth Engine rejected the request (HTTP 400): {error_text}"
                ) from last_error

            is_quota = _is_account_error(error_text)
            if attempt < max_retries:
                wait = delay * (2 if is_quota else 1)
                logger.warning(
                    "GeoTIFF download failed — retrying",
                    attempt=attempt,
                    error=error_text[:300],
                    retry_in_sec=wait,
                    is_quota_error=is_quota,
                )
                time.sleep(wait)
                delay *= retry_backoff
            else:
                logger.error(
                    "GeoTIFF download failed — retries exhausted",
                    attempt=attempt,
                    error=error_text[:300],
                )

        raise RuntimeError(
            f"GeoTIFF download failed after {max_retries} attempts: {last_error}"
        )

    def export_geotiff_split(
        self,
        composite: Any,
        bbox: Tuple[float, float, float, float],
        dest_path: Path,
        max_splits: int = 2,
        **kwargs: Any,
    ) -> Path:
        """``export_geotiff`` for a bbox, falling back to 2 × 2 parts.

        When Earth Engine answers "User memory limit exceeded", the bbox is
        downloaded as four quarters (recursively, up to ``max_splits``
        levels = 16 parts) and stitched locally into ``dest_path``. All parts
        use the same fixed global pixel grid, so the result is identical to
        a single download.
        """
        try:
            return self.export_geotiff(
                composite, self.build_aoi_from_bbox(*bbox), dest_path, **kwargs
            )
        except EarthEngineMemoryError:
            if max_splits <= 0:
                raise
            logger.warning(
                "Memory limit — downloading tile in 4 parts",
                dest=str(dest_path),
                levels_left=max_splits - 1,
            )

        west, south, east, north = bbox
        mid_x, mid_y = (west + east) / 2, (south + north) / 2
        quarters = [
            (west, south, mid_x, mid_y),
            (mid_x, south, east, mid_y),
            (west, mid_y, mid_x, north),
            (mid_x, mid_y, east, north),
        ]
        parts = [
            dest_path.with_name(f"{dest_path.stem}.part{i}{dest_path.suffix}")
            for i in range(len(quarters))
        ]
        try:
            for quarter, part in zip(quarters, parts):
                self.export_geotiff_split(
                    composite, quarter, part, max_splits=max_splits - 1, **kwargs
                )
            mosaic_geotiffs(parts, dest_path)
        finally:
            for part in parts:
                part.unlink(missing_ok=True)
        return dest_path

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

        # Same pixel grid and nodata convention as export_geotiff();
        # an explicit ``scale`` overrides the fixed grid.
        grid = (
            {"scale": scale}
            if scale is not None
            else {"crsTransform": list(GEE_CRS_TRANSFORM)}
        )
        composite = composite.unmask(S2_NODATA, False)

        description = f"lake_{lake_id:06d}_{year}"
        file_prefix = f"lake_{lake_id:06d}"

        task = ee.batch.Export.image.toDrive(
            image=composite,
            description=description,
            folder=folder,
            fileNamePrefix=file_prefix,
            region=aoi,
            crs=self._cfg.output_crs,
            **grid,
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
