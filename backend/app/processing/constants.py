"""Configurable constants for the lake feature extraction pipeline.

All tuneable thresholds and parameters are centralised here so that
processing modules never hardcode magic numbers.
"""

from __future__ import annotations

from typing import Final

from app.ML_pipeline.constants import (
    S2_BAND_CLEAR_COUNT,
    S2_BANDS_DOWNLOAD,
    S2_BANDS_SPECTRAL,
)

# ── Band Index Mapping ────────────────────────────────────────────────────────
# Positions in the merged GeoTIFF, looked up by name from S2_BANDS_DOWNLOAD
# so they can never drift out of sync with the download order.
COASTAL: Final[int] = S2_BANDS_DOWNLOAD.index("B1")     # 443 nm
BLUE: Final[int] = S2_BANDS_DOWNLOAD.index("B2")        # 490 nm
GREEN: Final[int] = S2_BANDS_DOWNLOAD.index("B3")       # 560 nm
RED: Final[int] = S2_BANDS_DOWNLOAD.index("B4")         # 665 nm
RE1: Final[int] = S2_BANDS_DOWNLOAD.index("B5")         # Red Edge 1, 705 nm
RE2: Final[int] = S2_BANDS_DOWNLOAD.index("B6")         # Red Edge 2, 740 nm
RE3: Final[int] = S2_BANDS_DOWNLOAD.index("B7")         # Red Edge 3, 783 nm
NIR: Final[int] = S2_BANDS_DOWNLOAD.index("B8")         # NIR broad, 842 nm
NIR_NARROW: Final[int] = S2_BANDS_DOWNLOAD.index("B8A") # NIR narrow, 865 nm
SWIR1: Final[int] = S2_BANDS_DOWNLOAD.index("B11")      # 1610 nm
SWIR2: Final[int] = S2_BANDS_DOWNLOAD.index("B12")      # 2190 nm
CLEAR_COUNT: Final[int] = S2_BANDS_DOWNLOAD.index(S2_BAND_CLEAR_COUNT)

# Spectral bands only (the QA band is handled separately)
BAND_NAMES: Final[list] = [b.lower() for b in S2_BANDS_SPECTRAL]
NUM_BANDS: Final[int] = len(S2_BANDS_SPECTRAL)
# Total bands in the downloaded GeoTIFF (spectral + QA)
STACK_BAND_COUNT: Final[int] = len(S2_BANDS_DOWNLOAD)

# Spectral bands must come first so ``stack[:NUM_BANDS]`` is the spectral cube
assert S2_BANDS_DOWNLOAD[:NUM_BANDS] == S2_BANDS_SPECTRAL

# Sentinel-2 L2A surface reflectance is stored as reflectance × 10000.
# Indices with additive constants (EVI, SAVI, MSAVI, AWEI) require true
# reflectance in [0, 1]; ratio-only indices are scale-invariant.
REFLECTANCE_SCALE: Final[float] = 10000.0

# Stored in lake_features.feature_version. Bump whenever bands, resolution,
# or formulas change, so the generator recomputes older rows.
#   1 = 10 m, B2-B7 only, proxy NIR/SWIR (legacy)
#   2 = 30 m single stack (B1-B12 + CLEAR_COUNT), true NIR/SWIR, reflectance
FEATURE_VERSION: Final[int] = 2

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
