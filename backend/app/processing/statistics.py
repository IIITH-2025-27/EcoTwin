"""Compute band, pixel, water, and spectral summary statistics.

All functions operate on NumPy arrays and ignore NoData pixels.
Thresholds are imported from the centralised constants module.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pyproj

from app.processing.constants import (
    BAND_NAMES,
    BLUE,
    EPSILON,
    GREEN,
    MNDWI_WATER_THRESHOLD,
    NDVI_VEGETATION_THRESHOLD,
    NDVI_WATER_MAX,
    NDWI_WATER_THRESHOLD,
    NIR,
    NUM_BANDS,
    RED,
    SWIR,
)


# ── Band Statistics ───────────────────────────────────────────────────────────


def compute_band_statistics(
    bands: np.ndarray,
    nodata: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Per-band mean/std/min/max/median for B2–B7.

    Parameters
    ----------
    bands : (6, H, W) float32 array
    nodata : nodata sentinel value

    Returns
    -------
    Dict with keys like 'b2_mean', 'b3_std', 'b4_median', etc.
    """
    result: Dict[str, Optional[float]] = {}

    for i, name in enumerate(BAND_NAMES):
        band = bands[i]
        if nodata is not None:
            valid = band[band != nodata]
        else:
            valid = band[np.isfinite(band)]

        if valid.size == 0:
            for stat in ("mean", "std", "min", "max", "median"):
                result[f"{name}_{stat}"] = None
        else:
            result[f"{name}_mean"] = float(np.mean(valid))
            result[f"{name}_std"] = float(np.std(valid))
            result[f"{name}_min"] = float(np.min(valid))
            result[f"{name}_max"] = float(np.max(valid))
            result[f"{name}_median"] = float(np.median(valid))

    return result


def compute_single_band_statistics(
    band: np.ndarray,
    name: str,
    nodata: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Mean/std/min/max/median for one named band.

    Same computation as ``compute_band_statistics``, but for a single band
    fetched outside the standard B2-B7 set (e.g. B8), which isn't part of
    ``BAND_NAMES``/``NUM_BANDS``.

    Parameters
    ----------
    band : (H, W) float32 array
    name : band name prefix for the result keys, e.g. "b8"
    nodata : nodata sentinel value
    """
    if nodata is not None:
        valid = band[band != nodata]
    else:
        valid = band[np.isfinite(band)]

    if valid.size == 0:
        return {f"{name}_{stat}": None for stat in ("mean", "std", "min", "max", "median")}

    return {
        f"{name}_mean": float(np.mean(valid)),
        f"{name}_std": float(np.std(valid)),
        f"{name}_min": float(np.min(valid)),
        f"{name}_max": float(np.max(valid)),
        f"{name}_median": float(np.median(valid)),
    }


# ── Pixel Statistics ──────────────────────────────────────────────────────────


def compute_pixel_statistics(
    bands: np.ndarray,
    nodata: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Pixel count statistics.

    Parameters
    ----------
    bands : (6, H, W) float32 array
    nodata : nodata sentinel value

    Returns
    -------
    Dict with pixel_count, valid_pixel_count, nodata_pixel_count,
    coverage_percent, cloud_percent, valid_pixel_ratio,
    masked_pixel_percentage.
    """
    total_pixels = int(bands.shape[1] * bands.shape[2])

    if nodata is not None:
        # A pixel is valid if ALL bands have non-nodata values
        valid_mask = np.all(bands != nodata, axis=0)
    else:
        valid_mask = np.all(np.isfinite(bands), axis=0)

    valid_count = int(np.sum(valid_mask))
    nodata_count = total_pixels - valid_count
    coverage = (valid_count / total_pixels * 100.0) if total_pixels > 0 else 0.0

    # Approximate cloud percentage as nodata fraction
    # (clouds are masked to nodata in the GEE composite pipeline)
    cloud_pct = (nodata_count / total_pixels * 100.0) if total_pixels > 0 else 0.0

    # Extra metrics (item #8)
    valid_ratio = (valid_count / total_pixels) if total_pixels > 0 else 0.0
    masked_pct = cloud_pct  # masked = nodata (same as cloud proxy)

    return {
        "pixel_count": total_pixels,
        "valid_pixel_count": valid_count,
        "nodata_pixel_count": nodata_count,
        "coverage_percent": round(coverage, 4),
        "cloud_percent": round(cloud_pct, 4),
        "valid_pixel_ratio": round(valid_ratio, 6),
        "masked_pixel_percentage": round(masked_pct, 4),
    }


# ── Water Statistics ──────────────────────────────────────────────────────────


def compute_water_statistics(
    ndwi_array: np.ndarray,
    mndwi_array: np.ndarray,
    ndvi_array: np.ndarray,
    pixel_size_x: float,
    pixel_size_y: float,
    crs: str,
    raster_transform=None,
) -> Dict[str, Optional[float]]:
    """Classify pixels as water/vegetation/soil using a robust multi-index rule.

    Water classification (tuned for Indian lakes):
        Water = (MNDWI > MNDWI_WATER_THRESHOLD)
                OR (NDWI > NDWI_WATER_THRESHOLD AND NDVI < NDVI_WATER_MAX)

    Vegetation:
        NDVI > NDVI_VEGETATION_THRESHOLD  (non-water pixels only)

    Remaining valid pixels → soil.

    Water area uses geodesic computation for geographic CRS (EPSG:4326).

    Parameters
    ----------
    ndwi_array : (H, W) float32 with NaN for invalid pixels
    mndwi_array : (H, W) float32 with NaN for invalid pixels
    ndvi_array : (H, W) float32 with NaN for invalid pixels
    pixel_size_x, pixel_size_y : pixel dimensions in CRS units
    crs : the raster CRS (e.g. 'EPSG:4326')
    raster_transform : rasterio Affine transform (needed for geodesic area)

    Returns
    -------
    Dict with water/vegetation/soil counts, percentages, water_area_sqkm,
    and water_to_land_ratio.
    """
    valid = (
        np.isfinite(ndwi_array)
        & np.isfinite(mndwi_array)
        & np.isfinite(ndvi_array)
    )
    valid_count = int(np.sum(valid))

    empty_result = {
        "water_pixels": 0,
        "vegetation_pixels": 0,
        "soil_pixels": 0,
        "water_percentage": 0.0,
        "vegetation_percentage": 0.0,
        "soil_percentage": 0.0,
        "water_area_sqkm": 0.0,
        "water_to_land_ratio": 0.0,
    }

    if valid_count == 0:
        return empty_result

    # ── Robust multi-index water classification ───────────────────────────
    mndwi_water = valid & (mndwi_array > MNDWI_WATER_THRESHOLD)
    ndwi_ndvi_water = valid & (
        (ndwi_array > NDWI_WATER_THRESHOLD) & (ndvi_array < NDVI_WATER_MAX)
    )
    water_mask = mndwi_water | ndwi_ndvi_water

    vegetation_mask = valid & (~water_mask) & (ndvi_array > NDVI_VEGETATION_THRESHOLD)
    soil_mask = valid & (~water_mask) & (~vegetation_mask)

    water_px = int(np.sum(water_mask))
    veg_px = int(np.sum(vegetation_mask))
    soil_px = int(np.sum(soil_mask))
    land_px = veg_px + soil_px

    water_pct = (water_px / valid_count * 100.0) if valid_count > 0 else 0.0
    veg_pct = (veg_px / valid_count * 100.0) if valid_count > 0 else 0.0
    soil_pct = (soil_px / valid_count * 100.0) if valid_count > 0 else 0.0

    # ── Accurate water area computation ───────────────────────────────────
    pixel_area_sqm = _pixel_area_sqm(
        pixel_size_x, pixel_size_y, crs, raster_transform
    )
    water_area_sqkm = (water_px * pixel_area_sqm) / 1e6

    # Water-to-land ratio
    water_to_land = (water_px / land_px) if land_px > 0 else 0.0

    return {
        "water_pixels": water_px,
        "vegetation_pixels": veg_px,
        "soil_pixels": soil_px,
        "water_percentage": round(water_pct, 4),
        "vegetation_percentage": round(veg_pct, 4),
        "soil_percentage": round(soil_pct, 4),
        "water_area_sqkm": round(water_area_sqkm, 6),
        "water_to_land_ratio": round(water_to_land, 6),
    }


def _pixel_area_sqm(
    pixel_size_x: float,
    pixel_size_y: float,
    crs: str,
    raster_transform=None,
) -> float:
    """Compute pixel area in square metres.

    For geographic CRS (EPSG:4326), uses ``pyproj.Geod`` for geodesic
    computation.  For projected CRS, the pixel sizes are already in
    linear units.
    """
    crs_str = str(crs).upper()

    if "4326" in crs_str or "GEOGRAPHIC" in crs_str:
        # Geodesic approach: compute the area of one pixel as a polygon
        # on the WGS84 ellipsoid using pyproj.Geod
        geod = pyproj.Geod(ellps="WGS84")

        # Representative latitude: use the centre of the raster if
        # a transform is available, otherwise assume mid-latitude.
        if raster_transform is not None:
            # raster_transform.f is the top-left y coordinate (latitude)
            # raster_transform.e is the negative pixel height
            centre_lat = raster_transform.f + raster_transform.e * 0.5
        else:
            centre_lat = 20.0  # fallback: approximate centre of India

        # Build a single-pixel polygon at the representative latitude
        lon0 = 0.0  # longitude doesn't affect area for a small rect
        lat0 = centre_lat
        lons = [
            lon0,
            lon0 + pixel_size_x,
            lon0 + pixel_size_x,
            lon0,
            lon0,
        ]
        lats = [
            lat0,
            lat0,
            lat0 - pixel_size_y,
            lat0 - pixel_size_y,
            lat0,
        ]
        area_sqm, _ = geod.polygon_area_perimeter(lons, lats)
        return abs(area_sqm)
    else:
        # Projected CRS — pixel sizes already in CRS units (usually metres)
        return abs(pixel_size_x * pixel_size_y)


# ── Spectral Summary ─────────────────────────────────────────────────────────


def compute_spectral_summary(
    bands: np.ndarray,
    nodata: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Compute spectral summary features.

    These are simplified spectral metrics (not true Tasseled Cap):
    - visible_brightness: mean of visible bands (B2, B3, B4)
    - nir_red_difference: mean(NIR − RED) across valid pixels
    - green_swir_difference: mean(GREEN − SWIR) across valid pixels
    - spectral_variance: mean of per-pixel variance across 6 bands
    - spectral_entropy: normalised Shannon entropy of band means (0–1)

    Parameters
    ----------
    bands : (6, H, W) float32 array
    nodata : nodata sentinel value

    Returns
    -------
    Dict with visible_brightness, nir_red_difference,
    green_swir_difference, spectral_variance, spectral_entropy.
    """
    if nodata is not None:
        valid = np.all(bands != nodata, axis=0)
    else:
        valid = np.all(np.isfinite(bands), axis=0)

    valid_count = int(np.sum(valid))
    if valid_count == 0:
        return {
            "visible_brightness": None,
            "nir_red_difference": None,
            "green_swir_difference": None,
            "spectral_variance": None,
            "spectral_entropy": None,
        }

    # Extract valid pixels for each band → (6, N)
    valid_bands = bands[:, valid]

    # Visible brightness: mean of B2, B3, B4 across all valid pixels
    visible_brightness = float(np.mean(valid_bands[:3]))

    # NIR − RED difference (proxy for vegetation vigour)
    nir_red_difference = float(np.mean(valid_bands[NIR] - valid_bands[RED]))

    # GREEN − SWIR difference (proxy for moisture)
    green_swir_difference = float(np.mean(valid_bands[GREEN] - valid_bands[SWIR]))

    # Spectral Variance: per-pixel variance across 6 bands, then mean
    per_pixel_var = np.var(valid_bands, axis=0)
    spectral_variance = float(np.mean(per_pixel_var))

    # Normalised Spectral Entropy: Shannon entropy / log₂(num_bands)
    # Range: 0 (all energy in one band) to 1 (uniform distribution)
    band_means = np.mean(valid_bands, axis=1)  # (6,)
    total = np.sum(band_means)
    if total > EPSILON:
        probs = band_means / total
        probs = probs[probs > 0]
        raw_entropy = float(-np.sum(probs * np.log2(probs)))
        max_entropy = np.log2(NUM_BANDS)  # log₂(6) ≈ 2.585
        spectral_entropy = raw_entropy / max_entropy if max_entropy > 0 else 0.0
    else:
        spectral_entropy = 0.0

    return {
        "visible_brightness": round(visible_brightness, 6),
        "nir_red_difference": round(nir_red_difference, 6),
        "green_swir_difference": round(green_swir_difference, 6),
        "spectral_variance": round(spectral_variance, 6),
        "spectral_entropy": round(spectral_entropy, 6),
    }
