"""Ecological index computation from Sentinel-2 band means.

Computes indices from the band set available per lake-year: B2-B7 (always,
from the merged imagery pipeline) plus B8 (NIR, when
``lake_features.b8_status == 'completed'`` — fetched separately via
``app/services/b8_feature_generator.py``, server-side reduceRegions, no
raster download).

NDVI and NDWI use the *standard* formulas with true NIR (B8) now that it's
available — previously these were B7-based proxies (B7 = Red Edge 3,
783nm) because B8 hadn't been fetched at all. NDCI, Turbidity Ratio, and
Red Edge Slope never needed NIR and are unchanged.

Each index is computed independently: a lake-year missing B8 (not yet
fetched, or fetch failed) still gets NDCI/Turbidity/Red-Edge-Slope — only
NDVI and NDWI become ``None`` for that row, rather than the whole result
going empty. This matters because B8 backfill lags behind the main B2-B7
pipeline for many lake-years.

All formulas use the **mean** reflectance value of each band per
lake-year, as required by the forecasting spec.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

# Same epsilon used by app/processing/spectral_indices.py
_EPSILON: float = 1e-10

# Sentinel-2 central wavelengths used for Red Edge Slope: B5 = 705nm, B7 = 783nm
_RED_EDGE_DELTA_LAMBDA: float = 783.0 - 705.0  # 78 nm


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Divide two scalars, returning 0.0 when denominator is near zero."""
    if abs(denominator) < _EPSILON:
        return 0.0
    return numerator / denominator


def _clean(value: Optional[float]) -> Optional[float]:
    """Return a finite float, or None if the value is missing/non-finite."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def compute_ecological_indices(
    b2_mean: Optional[float],
    b3_mean: Optional[float],
    b4_mean: Optional[float],
    b5_mean: Optional[float],
    b6_mean: Optional[float],
    b7_mean: Optional[float],
    b8_mean: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Compute the five ecological indices from per-band mean reflectances.

    Parameters
    ----------
    b2_mean - b8_mean : Mean reflectance for Sentinel-2 bands B2-B8.
        ``b8_mean`` is optional (defaults to None) since B8 fetch coverage
        lags the main pipeline; indices that need it (NDVI, NDWI) are
        ``None`` for a row until B8 is available for that lake-year.

    Returns
    -------
    Dict with keys ``ndci``, ``ndvi``, ``ndwi``, ``turbidity_ratio``,
    ``red_edge_slope``. Each value is ``None`` only if *that specific
    index's* required bands are missing — not tied to the other indices.

    Index definitions
    ------------------
    NDCI             (B5 − B4) / (B5 + B4)        Chlorophyll-a / algal bloom
    NDVI             (B8 − B4) / (B8 + B4)         Vegetation vigor (standard formula)
    NDWI             (B3 − B8) / (B3 + B8)         Water mask (McFeeters, standard formula)
    Turbidity Ratio  (B4 − B3) / (B4 + B3)         Water clarity / sediment
    Red Edge Slope   (B7 − B5) / (783 − 705)       Pigment concentration trend
    """
    result: Dict[str, Optional[float]] = {
        "ndci": None,
        "ndvi": None,
        "ndwi": None,
        "turbidity_ratio": None,
        "red_edge_slope": None,
    }

    b3 = _clean(b3_mean)
    b4 = _clean(b4_mean)
    b5 = _clean(b5_mean)
    b7 = _clean(b7_mean)
    b8 = _clean(b8_mean)
    # b2_mean / b6_mean are part of the standard band set fetched per
    # lake-year but aren't inputs to any of these five formulas.

    if b5 is not None and b4 is not None:
        result["ndci"] = _safe_ratio(b5 - b4, b5 + b4)

    if b8 is not None and b4 is not None:
        result["ndvi"] = _safe_ratio(b8 - b4, b8 + b4)

    if b3 is not None and b8 is not None:
        result["ndwi"] = _safe_ratio(b3 - b8, b3 + b8)

    if b4 is not None and b3 is not None:
        result["turbidity_ratio"] = _safe_ratio(b4 - b3, b4 + b3)

    if b7 is not None and b5 is not None:
        result["red_edge_slope"] = (b7 - b5) / _RED_EDGE_DELTA_LAMBDA

    return result
