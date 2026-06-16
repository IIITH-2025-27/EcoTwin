"""
Phase 1 — Google Earth Engine ingestion.

Fetches an annual Sentinel-2 SR composite for a given (region, year),
computes NDVI / NDWI / NBR spectral indices, reduces them to per-region
summary statistics, and downloads the raw multi-band array needed by the
Prithvi encoder in Phase 2.

External dependency:
    earthengine-api  (pip install earthengine-api)
    Authentication:  run `earthengine authenticate` once, or supply a
                     service-account key via GEE_SERVICE_ACCOUNT_KEY_PATH env.

Nothing in this module touches the database — all persistence is handled
by the Celery tasks in pipeline.py.
"""

from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

from app.ML_pipeline.constants import (
    GEE_BBOX_HALF_DEG,
    GEE_CLOUD_COVER_MAX,
    GEE_COMPOSITE_METHOD,
    GEE_CRS,
    GEE_MAX_PIXELS,
    GEE_REQUEST_TIMEOUT_SEC,
    GEE_SCALE_METRES,
    GEE_SENTINEL2_COLLECTION,
    NBR_NIR_BAND,
    NBR_SWIR2_BAND,
    NDVI_NIR_BAND,
    NDVI_RED_BAND,
    NDWI_GREEN_BAND,
    NDWI_NIR_BAND,
    PRITHVI_PATCH_SIZE_PX,
    PRITHVI_REFLECTANCE_SCALE,
    S2_BANDS_PRITHVI,
)

logger = structlog.get_logger(__name__)


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class IndexStats:
    """Per-region summary statistics for one spectral index."""

    mean:   float = 0.0
    std:    float = 0.0
    median: float = 0.0
    min:    float = 0.0
    max:    float = 0.0


@dataclass
class GEECompositeResult:
    """All outputs produced by a single GEE composite request."""

    region_id:   str
    year:        int
    ndvi:        IndexStats = field(default_factory=IndexStats)
    ndwi:        IndexStats = field(default_factory=IndexStats)
    nbr:         IndexStats = field(default_factory=IndexStats)
    # (num_bands, H, W) float32 in [0, 1] — None when download fails
    band_array:  Optional[np.ndarray] = None
    pixel_count: int = 0


# ── GEE helpers ────────────────────────────────────────────────────────────────

def _require_ee():
    """Import earthengine-api or raise a clear error."""
    try:
        import ee  # noqa: PLC0415
        return ee
    except ImportError as exc:
        raise RuntimeError(
            "earthengine-api is not installed. "
            "Run: pip install earthengine-api  then  earthengine authenticate"
        ) from exc


def _build_aoi(ee, center_lat: float, center_lon: float):
    """Return a GEE BBox geometry centred on the region (~5 km × 5 km)."""
    half = GEE_BBOX_HALF_DEG
    return ee.Geometry.BBox(
        center_lon - half,
        center_lat - half,
        center_lon + half,
        center_lat + half,
    )


def _date_range(year: int) -> tuple[str, str]:
    return f"{year}-01-01", f"{year}-12-31"


def _add_indices(ee, image):
    """Compute NDVI, NDWI, NBR and attach them as new bands."""
    ndvi = image.normalizedDifference([NDVI_NIR_BAND, NDVI_RED_BAND]).rename("NDVI")
    ndwi = image.normalizedDifference([NDWI_GREEN_BAND, NDWI_NIR_BAND]).rename("NDWI")
    nbr  = image.normalizedDifference([NBR_NIR_BAND, NBR_SWIR2_BAND]).rename("NBR")
    return image.addBands([ndvi, ndwi, nbr])


def _parse_stats(raw: dict, prefix: str) -> IndexStats:
    """Extract mean/std/min/max from a GEE reduceRegion result dict."""
    return IndexStats(
        mean   = float(raw.get(f"{prefix}_mean",   0.0)),
        std    = float(raw.get(f"{prefix}_stdDev", 0.0)),
        # GEE median requires a separate reducer; fall back to mean when absent
        median = float(raw.get(f"{prefix}_median", raw.get(f"{prefix}_mean", 0.0))),
        min    = float(raw.get(f"{prefix}_min",    0.0)),
        max    = float(raw.get(f"{prefix}_max",    0.0)),
    )


def _build_composite(ee, aoi, year: int):
    """Filter and composite the Sentinel-2 collection for the given year/AOI."""
    start, end = _date_range(year)

    col = (
        ee.ImageCollection(GEE_SENTINEL2_COLLECTION)
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", GEE_CLOUD_COVER_MAX))
        .map(lambda img: _add_indices(ee, img))
    )

    if GEE_COMPOSITE_METHOD == "median":
        return col.median()
    if GEE_COMPOSITE_METHOD == "mean":
        return col.mean()
    return col.mosaic()  # most-recent pixel per location


def _reduce_indices(ee, composite, aoi) -> dict:
    """Reduce NDVI/NDWI/NBR over the AOI; returns raw GEE stats dict."""
    reducer = (
        ee.Reducer.mean()
        .combine(ee.Reducer.stdDev(), sharedInputs=True)
        .combine(ee.Reducer.min(),    sharedInputs=True)
        .combine(ee.Reducer.max(),    sharedInputs=True)
    )
    return (
        composite.select(["NDVI", "NDWI", "NBR"])
        .reduceRegion(
            reducer=reducer,
            geometry=aoi,
            scale=GEE_SCALE_METRES,
            crs=GEE_CRS,
            maxPixels=GEE_MAX_PIXELS,
            bestEffort=True,
        )
        .getInfo()       # ← network call
    )


def _count_pixels(ee, composite, aoi) -> int:
    """Return the number of valid NDVI pixels (data quality indicator)."""
    result = (
        composite.select("NDVI")
        .reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=aoi,
            scale=GEE_SCALE_METRES,
            maxPixels=GEE_MAX_PIXELS,
        )
        .getInfo()
    )
    return int(result.get("NDVI", 0))


def _download_band_array(ee, composite, aoi) -> Optional[np.ndarray]:
    """
    Download the Prithvi input bands as a (C, H, W) float32 array.

    Returns None on any failure — the pipeline can still proceed to the
    DB insert; Phase 2 will re-fetch when needed.
    """
    try:
        url = composite.select(S2_BANDS_PRITHVI).getThumbURL({
            "min": 0,
            "max": 3000,
            "dimensions": PRITHVI_PATCH_SIZE_PX,
            "region": aoi,
            "format": "NPY",
            "crs": GEE_CRS,
        })
        with urllib.request.urlopen(url, timeout=GEE_REQUEST_TIMEOUT_SEC) as resp:
            raw_bytes = resp.read()

        arr = np.load(io.BytesIO(raw_bytes))                 # (H, W, C)
        arr = arr.astype(np.float32) / PRITHVI_REFLECTANCE_SCALE
        arr = np.clip(arr, 0.0, 1.0)
        arr = np.transpose(arr, (2, 0, 1))                   # → (C, H, W)
        return arr

    except Exception as exc:
        logger.warning(
            "Band array download failed — embedding will use stub in Phase 2",
            error=str(exc),
        )
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_composite(
    region_id: str,
    center_lat: float,
    center_lon: float,
    year: int,
) -> GEECompositeResult:
    """
    Fetch a Sentinel-2 annual composite and compute spectral index statistics.

    Args:
        region_id:  UUID string (used only for logging).
        center_lat: Region centre latitude  [-90, 90].
        center_lon: Region centre longitude [-180, 180].
        year:       Four-digit year for the annual composite.

    Returns:
        GEECompositeResult with NDVI/NDWI/NBR stats and optional band_array.

    Raises:
        RuntimeError: if earthengine-api is not installed or not authenticated.
    """
    ee = _require_ee()
    log = logger.bind(region_id=region_id, year=year)
    log.info("GEE composite fetch started")

    aoi = _build_aoi(ee, center_lat, center_lon)
    composite = _build_composite(ee, aoi, year)

    stats_raw    = _reduce_indices(ee, composite, aoi)
    pixel_count  = _count_pixels(ee, composite, aoi)
    band_array   = _download_band_array(ee, composite, aoi)

    result = GEECompositeResult(
        region_id   = region_id,
        year        = year,
        ndvi        = _parse_stats(stats_raw, "NDVI"),
        ndwi        = _parse_stats(stats_raw, "NDWI"),
        nbr         = _parse_stats(stats_raw, "NBR"),
        band_array  = band_array,
        pixel_count = pixel_count,
    )

    log.info(
        "GEE composite fetch completed",
        ndvi_mean   = round(result.ndvi.mean, 4),
        ndwi_mean   = round(result.ndwi.mean, 4),
        nbr_mean    = round(result.nbr.mean, 4),
        pixel_count = pixel_count,
        band_array  = "ok" if band_array is not None else "missing",
    )
    return result
