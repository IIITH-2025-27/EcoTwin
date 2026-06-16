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
GEE_SCALE_METRES: Final[int] = 10             # Sentinel-2 native 10 m resolution
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

# Band order fed to Prithvi (must match model training config)
S2_BANDS_PRITHVI: Final[List[str]] = ["B2", "B3", "B4", "B8A", "B11", "B12"]

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
PRITHVI_NUM_FRAMES:    Final[int] = 1          # single annual composite
PRITHVI_NUM_BANDS:     Final[int] = 6
PRITHVI_HF_REPO:       Final[str] = "ibm-nasa-geospatial/Prithvi-100M"
# Overridden at runtime by PRITHVI_MODEL_PATH env var; see config.py
PRITHVI_LOCAL_WEIGHTS: Final[str] = "/app/models/prithvi_100m.pt"
# Sentinel-2 DN scale factor (reflectance = DN / PRITHVI_REFLECTANCE_SCALE)
PRITHVI_REFLECTANCE_SCALE: Final[float] = 10_000.0

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

# ── Celery Pipeline Queue ──────────────────────────────────────────────────────
PIPELINE_QUEUE:           Final[str] = "pipeline"
PIPELINE_MAX_RETRIES:     Final[int] = 3
PIPELINE_RETRY_DELAY_SEC: Final[int] = 60

# Bulk-ingestion settings (used by management scripts)
PIPELINE_BATCH_SIZE: Final[int] = 50     # number of regions per bulk-enqueue call
PIPELINE_YEAR_START: Final[int] = 2017   # earliest Sentinel-2 SR year
PIPELINE_YEAR_END:   Final[int] = 2024   # inclusive (update annually)
