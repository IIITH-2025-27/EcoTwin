"""
ML Pipeline constants.

All tuneable values live here.  Logic modules must never hardcode any of
these — always import from this file so they can be overridden centrally.
"""

from typing import Final, List

# ── Google Earth Engine ────────────────────────────────────────────────────────
GEE_SENTINEL2_COLLECTION: Final[str] = "COPERNICUS/S2_SR_HARMONIZED"
GEE_CLOUD_COVER_MAX: Final[int] = 20          # % — images with higher cover are excluded
GEE_COMPOSITE_METHOD: Final[str] = "median"   # "median" | "mean" | "mosaic"
# Output resolution of the per-lake-year download. 30 m matches Prithvi's
# HLS L30 pre-training scale, so the stack feeds the encoder without
# resampling; lake_features are computed from the same pixels.
GEE_SCALE_METRES: Final[int] = 30
# Fixed global pixel grid for downloads in GEE_CRS (EPSG:4326): pixel size is
# GEE_SCALE_METRES converted to degrees the way Earth Engine does (metres at
# the equator), origin at (0°, 0°). Every tile of every lake-year snaps to
# this one grid, so tiles merge without resampling and a lake's pixels line
# up across years.
GEE_PIXEL_DEG: Final[float] = GEE_SCALE_METRES / 111319.49079327357
GEE_CRS_TRANSFORM: Final[List[float]] = [GEE_PIXEL_DEG, 0, 0, 0, -GEE_PIXEL_DEG, 0]

# Per-pixel cloud/haze/shadow mask: Cloud Score+ (linked by system:index).
# cs_cdf is the cumulative clear-sky score; pixels below the threshold are
# masked before compositing. 0.6 is Google's suggested starting point.
GEE_CLOUD_SCORE_COLLECTION: Final[str] = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
GEE_CLOUD_SCORE_BAND: Final[str] = "cs_cdf"
GEE_CLOUD_SCORE_MIN: Final[float] = 0.6
GEE_CRS: Final[str] = "EPSG:4326"
GEE_REQUEST_TIMEOUT_SEC: Final[int] = 300
GEE_MAX_PIXELS: Final[float] = 1e9
# Half-side of the bounding box around the region centre (degrees, ~5 km at equator)
GEE_BBOX_HALF_DEG: Final[float] = 0.025

# Sentinel-2 SR band names used for index computation
S2_BAND_BLUE:  Final[str] = "B2"
S2_BAND_GREEN: Final[str] = "B3"
S2_BAND_RED:   Final[str] = "B4"
S2_BAND_NIR:   Final[str] = "B8"
S2_BAND_SWIR1: Final[str] = "B11"
S2_BAND_SWIR2: Final[str] = "B12"

# Single per-lake-year download stack. Every downstream consumer (Prithvi
# embeddings, lake_features, ecological forecast) reads from this one image,
# so the GeoTIFF band order below is the contract for all of them.
#   B1 Coastal aerosol, B2 Blue, B3 Green, B4 Red, B5/B6/B7 Red Edge 1-3,
#   B8 NIR (broad), B8A NIR (narrow), B11 SWIR1, B12 SWIR2
S2_BANDS_SPECTRAL: Final[List[str]] = [
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12",
]
# QA band appended after the spectral bands: number of cloud-free
# observations that went into each pixel's median (0 → pixel is nodata).
S2_BAND_CLEAR_COUNT: Final[str] = "CLEAR_COUNT"
S2_BANDS_DOWNLOAD: Final[List[str]] = S2_BANDS_SPECTRAL + [S2_BAND_CLEAR_COUNT]

# Band order fed to Prithvi. The model config lists B02..B07, but those are
# HLS L30 (Landsat-8) band numbers: Blue, Green, Red, Narrow NIR, SWIR1, SWIR2.
# The Sentinel-2 equivalents are B2, B3, B4, B8A, B11, B12 — NOT S2 B5-B7,
# which are red-edge bands the model never saw in pre-training.
S2_BANDS_PRITHVI: Final[List[str]] = ["B2", "B3", "B4", "B8A", "B11", "B12"]

# Nodata value written to downloaded uint16 GeoTIFFs for masked pixels
# (clouds, outside the AOI). 0 is not safe: very dark reflectance (e.g.
# SWIR over clear water) can legitimately be 0 in the uint16 SR data, and
# CLEAR_COUNT uses 0 for "no observations". Real S2 SR never reaches 65535.
S2_NODATA: Final[int] = 65535

# 0-based positions of the Prithvi bands inside the S2_BANDS_DOWNLOAD stack
PRITHVI_BAND_INDICES: Final[List[int]] = [
    S2_BANDS_DOWNLOAD.index(b) for b in S2_BANDS_PRITHVI
]

# ── Spectral Index Formulas ────────────────────────────────────────────────────
# NDVI = (NIR - RED)   / (NIR + RED)
NDVI_NIR_BAND: Final[str] = "B8"
NDVI_RED_BAND: Final[str] = "B4"

# NDWI = (GREEN - NIR) / (GREEN + NIR)
NDWI_GREEN_BAND: Final[str] = "B3"
NDWI_NIR_BAND:   Final[str] = "B8"

# NBR  = (NIR - SWIR2) / (NIR + SWIR2)
NBR_NIR_BAND:   Final[str] = "B8"
NBR_SWIR2_BAND: Final[str] = "B12"

# ── Prithvi Foundation Model ───────────────────────────────────────────────────
PRITHVI_EMBEDDING_DIM: Final[int] = 768
PRITHVI_PATCH_SIZE_PX: Final[int] = 224       # spatial crop (H, W) fed to model
PRITHVI_TOKEN_PX:      Final[int] = 16        # ViT patch: 16 px = 480 m at 30 m
PRITHVI_TOKEN_GRID:    Final[int] = PRITHVI_PATCH_SIZE_PX // PRITHVI_TOKEN_PX  # 14
# Bumped whenever the embedding method changes, stored on regions rows so
# vectors from different methods are never silently compared.
#   1 = 1 km cells at 10 m, B2-B7 (legacy)
#   2 = lake + 500 m shore tokens at 30 m, B2/B3/B4/B8A/B11/B12
EMBEDDING_VERSION:     Final[int] = 2
PRITHVI_NUM_FRAMES:    Final[int] = 1          # single annual composite
PRITHVI_NUM_BANDS:     Final[int] = 6
PRITHVI_DEPTH:         Final[int] = 12         # transformer encoder depth
PRITHVI_NUM_HEADS:     Final[int] = 12         # attention heads
PRITHVI_HF_REPO:       Final[str] = "ibm-nasa-geospatial/Prithvi-100M"
# Prefer the locally cloned Prithvi repository when available.
PRITHVI_LOCAL_WEIGHTS: Final[str] = "app/ML_models/Prithvi-EO-1.0-100M"

# Per-band normalisation (from Prithvi config.yaml train_params).
# Order matches S2_BANDS_PRITHVI: Blue, Green, Red, Narrow NIR, SWIR1, SWIR2
# (HLS names B02-B07 = Sentinel-2 B2, B3, B4, B8A, B11, B12).
PRITHVI_BAND_MEAN: Final[List[float]] = [
    775.2290211032589,
    1080.992780391705,
    1228.5855250417867,
    2497.2022620507532,
    2204.2139147975554,
    1610.8324823273745,
]
PRITHVI_BAND_STD: Final[List[float]] = [
    1281.526139861424,
    1270.0297974547493,
    1399.4802505642526,
    1368.3446143747644,
    1291.6764008585435,
    1154.505683480695,
]

# ── Ecosystem Classification ───────────────────────────────────────────────────
# Rule-based decision thresholds (applied to annual NDVI / NDWI / NBR means).
# Raise/lower these to tune class boundaries without touching logic code.
ECOSYSTEM_DENSE_FOREST_NDVI_MIN: Final[float] = 0.60
ECOSYSTEM_OPEN_FOREST_NDVI_MIN:  Final[float] = 0.40
ECOSYSTEM_GRASSLAND_NDVI_MIN:    Final[float] = 0.30
ECOSYSTEM_CROPLAND_NDVI_MIN:     Final[float] = 0.15
ECOSYSTEM_WETLAND_NDWI_MIN:      Final[float] = 0.20
ECOSYSTEM_BURNED_NBR_MAX:        Final[float] = -0.10
ECOSYSTEM_BARREN_NDVI_MAX:       Final[float] = 0.10
ECOSYSTEM_CROPLAND_NDWI_MAX:     Final[float] = -0.10   # irrigated cropland has higher NDWI

# Ordered from most-specific to most-general (rule evaluation order)
ECOSYSTEM_LABELS: Final[List[str]] = [
    "burned_disturbed",
    "wetland_water",
    "dense_forest",
    "open_forest",
    "grassland_shrub",
    "cropland",
    "barren_urban",
    "mixed_vegetation",
]

# Minimum confidence score returned by the rule classifier
ECOSYSTEM_MIN_CONFIDENCE: Final[float] = 0.35

# Bulk-ingestion settings
PIPELINE_BATCH_SIZE: Final[int] = 50     # number of regions per bulk operation
PIPELINE_YEAR_START: Final[int] = 2015   # earliest year available in the sync dropdown
PIPELINE_YEAR_END:   Final[int] = 2025   # inclusive (update annually)
