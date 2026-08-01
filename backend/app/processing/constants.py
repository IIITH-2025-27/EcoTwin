"""Configurable constants for the lake feature extraction pipeline.

All tuneable thresholds and parameters are centralised here so that
processing modules never hardcode magic numbers.
"""

from __future__ import annotations

from typing import Final

# ── Band Index Mapping ────────────────────────────────────────────────────────
# Order in the merged Sentinel-2 GeoTIFF (B2–B7, Prithvi bands)
BLUE: Final[int] = 0    # B2
GREEN: Final[int] = 1   # B3
RED: Final[int] = 2     # B4
NIR: Final[int] = 3     # B5 (Red Edge → NIR proxy)
RE2: Final[int] = 4     # B6 (Red Edge 2)
SWIR: Final[int] = 5    # B7 (Red Edge 3 → SWIR proxy)

BAND_NAMES: Final[list] = ["b2", "b3", "b4", "b5", "b6", "b7"]
NUM_BANDS: Final[int] = 6

# ── Water Classification Thresholds ───────────────────────────────────────────
# Robust multi-index classification for Indian lakes:
#   Water = (MNDWI > MNDWI_WATER_THRESHOLD)
#           OR (NDWI > NDWI_WATER_THRESHOLD AND NDVI < NDVI_WATER_MAX)
MNDWI_WATER_THRESHOLD: Final[float] = 0.0
NDWI_WATER_THRESHOLD: Final[float] = -0.05
NDVI_WATER_MAX: Final[float] = 0.1

# Vegetation: NDVI > this threshold (non-water pixels only)
NDVI_VEGETATION_THRESHOLD: Final[float] = 0.2

# Remaining valid pixels are classified as soil.

# ── GLCM Texture Configuration ────────────────────────────────────────────────
GLCM_BAND_INDEX: Final[int] = NIR      # Which band to compute GLCM on
GLCM_DISTANCE: Final[int] = 1          # Pixel distance for co-occurrence
GLCM_NUM_LEVELS: Final[int] = 64       # Grey-level quantisation levels

# ── Numerical Safety ─────────────────────────────────────────────────────────
EPSILON: Final[float] = 1e-10
