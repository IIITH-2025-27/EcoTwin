"""Ecological index computation from Sentinel-2 band means.

Computes indices that are *actually supported* by the available band set
(B2–B7 only).  Never references B8 (NIR), B11/B12 (SWIR), or any
thermal band — those are absent from the merged imagery.

All formulas use the **mean** reflectance value of each band per
lake-year, as required by the forecasting spec.
"""

from __future__ import annotations

from typing import Dict, Optional

# Same epsilon used by app/processing/spectral_indices.py
_EPSILON: float = 1e-10


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Divide two scalars, returning 0.0 when denominator is near zero."""
    if abs(denominator) < _EPSILON:
        return 0.0
    return numerator / denominator


def compute_ecological_indices(
    b2_mean: Optional[float],
    b3_mean: Optional[float],
    b4_mean: Optional[float],
    b5_mean: Optional[float],
    b6_mean: Optional[float],
    b7_mean: Optional[float],
) -> Dict[str, Optional[float]]:
    """Compute the four ecological indices from per-band mean reflectances.

    Parameters
    ----------
    b2_mean – b7_mean : Mean reflectance for Sentinel-2 bands B2–B7.
        Any ``None`` value causes the corresponding index to be ``None``.

    Returns
    -------
    Dict with keys ``ndci``, ``ndvi_b7``, ``turbidity_ratio``,
    ``red_edge_slope``.  Values are ``None`` when inputs are insufficient.

    Index definitions
    -----------------
    NDCI             (B5 − B4) / (B5 + B4)        Chlorophyll-a / algal bloom
    NDVI-B7 (proxy)  (B7 − B4) / (B7 + B4)        Vegetation vigor / greenness
    Turbidity Ratio  B4 / B3                       Water clarity / sediment
    Red Edge Slope   (B7 − B5) / (783 − 705)       Pigment concentration trend

    Sentinel-2 central wavelengths used for Red Edge Slope:
        B5 = 705 nm,  B7 = 783 nm  →  Δλ = 78 nm
    """
    result: Dict[str, Optional[float]] = {
        "ndci": None,
        "ndvi_b7": None,
        "turbidity_ratio": None,
        "red_edge_slope": None,
    }

    # Guard: if any required band is missing, return all-None
    if any(v is None for v in (b2_mean, b3_mean, b4_mean, b5_mean, b6_mean, b7_mean)):
        return result

    # At this point all values are guaranteed non-None; cast for mypy
    b4 = float(b4_mean)  # type: ignore[arg-type]
    b3 = float(b3_mean)  # type: ignore[arg-type]
    b5 = float(b5_mean)  # type: ignore[arg-type]
    b7 = float(b7_mean)  # type: ignore[arg-type]

    # NDCI = (B5 − B4) / (B5 + B4)
    result["ndci"] = _safe_ratio(b5 - b4, b5 + b4)

    # NDVI-B7 proxy = (B7 − B4) / (B7 + B4)
    result["ndvi_b7"] = _safe_ratio(b7 - b4, b7 + b4)

    # Turbidity Ratio = B4 / B3
    result["turbidity_ratio"] = _safe_ratio(b4, b3)

    # Red Edge Slope = (B7 − B5) / (783 − 705)
    _DELTA_LAMBDA = 783.0 - 705.0  # 78 nm
    result["red_edge_slope"] = (b7 - b5) / _DELTA_LAMBDA

    return result
