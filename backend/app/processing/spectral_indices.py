"""Compute spectral indices from Sentinel-2 bands.

The merged GeoTIFFs contain 6 Prithvi bands in order:
  Band 0 → B2 (Blue)
  Band 1 → B3 (Green)
  Band 2 → B4 (Red)
  Band 3 → B5 (Red Edge / NIR proxy)
  Band 4 → B6 (Red Edge 2)
  Band 5 → B7 (Red Edge 3 / SWIR proxy)

Since B8 (NIR), B11 (SWIR1), B12 (SWIR2) are absent from the merged
images, B5 is used as the NIR proxy and B7 as the SWIR proxy — consistent
with the existing Prithvi pipeline approach.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from app.processing.constants import (
    BLUE,
    EPSILON,
    GREEN,
    NIR,
    RE2,
    RED,
    SWIR,
)


def _safe_divide(
    numerator: np.ndarray,
    denominator: np.ndarray,
) -> np.ndarray:
    """Divide arrays, returning 0 where denominator is ~zero."""
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(
            np.abs(denominator) > EPSILON,
            numerator / denominator,
            0.0,
        )
    return result.astype(np.float32)


def _get_valid_mask(
    bands: np.ndarray,
    nodata: Optional[float],
) -> np.ndarray:
    """Return a boolean mask of valid (non-nodata) pixels.

    Parameters
    ----------
    bands : (C, H, W) array
    nodata : sentinel value (pixels equal to this are invalid)

    Returns
    -------
    (H, W) boolean array — True for valid pixels.
    """
    if nodata is None:
        return np.ones(bands.shape[1:], dtype=bool)
    # A pixel is valid if ALL bands have non-nodata values
    return np.all(bands != nodata, axis=0)


# ── Individual Index Functions ─────────────────────────────────────────────────

def compute_ndvi(bands: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - RED) / (NIR + RED)"""
    return _safe_divide(bands[NIR] - bands[RED], bands[NIR] + bands[RED])


def compute_evi(bands: np.ndarray) -> np.ndarray:
    """EVI = 2.5 × (NIR - RED) / (NIR + 6×RED - 7.5×BLUE + 1)"""
    denom = bands[NIR] + 6.0 * bands[RED] - 7.5 * bands[BLUE] + 1.0
    return _safe_divide(2.5 * (bands[NIR] - bands[RED]), denom)


def compute_savi(bands: np.ndarray, L: float = 0.5) -> np.ndarray:
    """SAVI = ((NIR - RED) / (NIR + RED + L)) × (1 + L)"""
    denom = bands[NIR] + bands[RED] + L
    return _safe_divide((bands[NIR] - bands[RED]) * (1.0 + L), denom)


def compute_msavi(bands: np.ndarray) -> np.ndarray:
    """MSAVI = (2×NIR + 1 - sqrt((2×NIR+1)² - 8×(NIR-RED))) / 2"""
    nir, red = bands[NIR], bands[RED]
    inner = (2.0 * nir + 1.0) ** 2 - 8.0 * (nir - red)
    inner = np.maximum(inner, 0.0)  # clamp negatives before sqrt
    return ((2.0 * nir + 1.0 - np.sqrt(inner)) / 2.0).astype(np.float32)


def compute_gci(bands: np.ndarray) -> np.ndarray:
    """GCI = (NIR / GREEN) - 1"""
    return (_safe_divide(bands[NIR], bands[GREEN]) - 1.0).astype(np.float32)


def compute_ndre(bands: np.ndarray) -> np.ndarray:
    """NDRE = (NIR - RE2) / (NIR + RE2)"""
    return _safe_divide(bands[NIR] - bands[RE2], bands[NIR] + bands[RE2])


def compute_ndwi(bands: np.ndarray) -> np.ndarray:
    """NDWI = (GREEN - NIR) / (GREEN + NIR)"""
    return _safe_divide(bands[GREEN] - bands[NIR], bands[GREEN] + bands[NIR])


def compute_mndwi(bands: np.ndarray) -> np.ndarray:
    """MNDWI = (GREEN - SWIR) / (GREEN + SWIR)"""
    return _safe_divide(bands[GREEN] - bands[SWIR], bands[GREEN] + bands[SWIR])


def compute_ndmi(bands: np.ndarray) -> np.ndarray:
    """NDMI = (NIR - SWIR) / (NIR + SWIR)"""
    return _safe_divide(bands[NIR] - bands[SWIR], bands[NIR] + bands[SWIR])


def compute_awei(bands: np.ndarray) -> np.ndarray:
    """AWEI = 4×(GREEN - SWIR) - (0.25×NIR + 2.75×SWIR)"""
    return (
        4.0 * (bands[GREEN] - bands[SWIR])
        - (0.25 * bands[NIR] + 2.75 * bands[SWIR])
    ).astype(np.float32)


def compute_nbr(bands: np.ndarray) -> np.ndarray:
    """NBR = (NIR - SWIR) / (NIR + SWIR)"""
    return _safe_divide(bands[NIR] - bands[SWIR], bands[NIR] + bands[SWIR])


def compute_nbr2(bands: np.ndarray) -> np.ndarray:
    """NBR2 = (RE2 - SWIR) / (RE2 + SWIR)"""
    return _safe_divide(bands[RE2] - bands[SWIR], bands[RE2] + bands[SWIR])


def compute_bsi(bands: np.ndarray) -> np.ndarray:
    """BSI = ((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))"""
    num = (bands[SWIR] + bands[RED]) - (bands[NIR] + bands[BLUE])
    den = (bands[SWIR] + bands[RED]) + (bands[NIR] + bands[BLUE])
    return _safe_divide(num, den)


def compute_ndbi(bands: np.ndarray) -> np.ndarray:
    """NDBI = (SWIR - NIR) / (SWIR + NIR)"""
    return _safe_divide(bands[SWIR] - bands[NIR], bands[SWIR] + bands[NIR])


# ── Aggregate Functions ────────────────────────────────────────────────────────

_INDEX_FUNCTIONS = {
    "ndvi": compute_ndvi,
    "evi": compute_evi,
    "savi": compute_savi,
    "msavi": compute_msavi,
    "gci": compute_gci,
    "ndre": compute_ndre,
    "ndwi": compute_ndwi,
    "mndwi": compute_mndwi,
    "ndmi": compute_ndmi,
    "awei": compute_awei,
    "nbr": compute_nbr,
    "nbr2": compute_nbr2,
    "bsi": compute_bsi,
    "ndbi": compute_ndbi,
}


def compute_all_indices(
    bands: np.ndarray,
    nodata: Optional[float] = None,
) -> Dict[str, np.ndarray]:
    """Compute all spectral indices, masking nodata pixels.

    Parameters
    ----------
    bands : (6, H, W) float32 array
    nodata : nodata sentinel value

    Returns
    -------
    Dict mapping index name → (H, W) float32 array (NaN where invalid).
    """
    valid = _get_valid_mask(bands, nodata)
    results: Dict[str, np.ndarray] = {}

    for name, fn in _INDEX_FUNCTIONS.items():
        arr = fn(bands)
        arr[~valid] = np.nan
        results[name] = arr

    return results


def compute_index_statistics(
    index_array: np.ndarray,
    full_stats: bool = False,
) -> Dict[str, Optional[float]]:
    """Compute summary statistics for a single spectral index.

    Parameters
    ----------
    index_array : (H, W) float32 array with NaN for invalid pixels
    full_stats : if True, include median/p25/p75 in addition to mean/std/min/max

    Returns
    -------
    Dict of statistic name → value (None if all pixels are invalid).
    """
    valid = index_array[np.isfinite(index_array)]
    if valid.size == 0:
        keys = ["mean", "std", "min", "max"]
        if full_stats:
            keys += ["median", "p25", "p75"]
        return {k: None for k in keys}

    stats: Dict[str, Optional[float]] = {
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
    }
    if full_stats:
        stats["median"] = float(np.median(valid))
        stats["p25"] = float(np.percentile(valid, 25))
        stats["p75"] = float(np.percentile(valid, 75))

    return stats
