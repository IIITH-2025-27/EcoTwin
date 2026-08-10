"""SQLAlchemy model for the lake_features table.

One row represents the ecological state of one lake for one year,
computed from the clipped Sentinel-2 image corresponding to that lake.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Double,
    Enum,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.db.base import Base

# Must match the Postgres enum created in migration 016
lake_feature_status = Enum(
    "pending",
    "processing",
    "completed",
    "failed",
    name="lake_feature_status",
    create_type=False,  # already exists via Alembic
)


class LakeFeature(Base):
    """Yearly ecological features extracted from Sentinel-2 imagery per lake."""

    __tablename__ = "lake_features"
    __table_args__ = (
        UniqueConstraint("lake_id", "year", name="uq_lake_features_lake_year"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── Identity ──────────────────────────────────────────────────────────
    lake_id = Column(BigInteger, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)

    # ── Processing ────────────────────────────────────────────────────────
    status = Column(
        lake_feature_status,
        nullable=False,
        server_default="pending",
        index=True,
    )
    feature_version = Column(
        Integer, nullable=False, server_default=text("1")
    )

    # ── Pixel Statistics ──────────────────────────────────────────────────
    pixel_count = Column(Integer, nullable=True)
    valid_pixel_count = Column(Integer, nullable=True)
    nodata_pixel_count = Column(Integer, nullable=True)
    coverage_percent = Column(Double, nullable=True)
    cloud_percent = Column(Double, nullable=True)

    # ── Sentinel-2 Band Statistics (B2–B7) ────────────────────────────────
    b2_mean = Column(Double, nullable=True)
    b2_std = Column(Double, nullable=True)
    b2_min = Column(Double, nullable=True)
    b2_max = Column(Double, nullable=True)
    b2_median = Column(Double, nullable=True)

    b3_mean = Column(Double, nullable=True)
    b3_std = Column(Double, nullable=True)
    b3_min = Column(Double, nullable=True)
    b3_max = Column(Double, nullable=True)
    b3_median = Column(Double, nullable=True)

    b4_mean = Column(Double, nullable=True)
    b4_std = Column(Double, nullable=True)
    b4_min = Column(Double, nullable=True)
    b4_max = Column(Double, nullable=True)
    b4_median = Column(Double, nullable=True)

    b5_mean = Column(Double, nullable=True)
    b5_std = Column(Double, nullable=True)
    b5_min = Column(Double, nullable=True)
    b5_max = Column(Double, nullable=True)
    b5_median = Column(Double, nullable=True)

    b6_mean = Column(Double, nullable=True)
    b6_std = Column(Double, nullable=True)
    b6_min = Column(Double, nullable=True)
    b6_max = Column(Double, nullable=True)
    b6_median = Column(Double, nullable=True)

    b7_mean = Column(Double, nullable=True)
    b7_std = Column(Double, nullable=True)
    b7_min = Column(Double, nullable=True)
    b7_max = Column(Double, nullable=True)
    b7_median = Column(Double, nullable=True)

    # ── Sentinel-2 Band Statistics (B8, NIR) ────────────────────────────────
    # Fetched separately from B2-B7 — B8 is not part of the Prithvi band set
    # used for embeddings, so it has its own dedicated acquisition pass.
    # See app/services/b8_feature_generator.py.
    # Plain text, not the lake_feature_status enum — kept independent of the
    # main pipeline's status type/state machine on purpose.
    b8_status = Column(
        String(20),
        nullable=False,
        server_default="pending",
        index=True,
    )
    b8_mean = Column(Double, nullable=True)
    b8_std = Column(Double, nullable=True)
    b8_min = Column(Double, nullable=True)
    b8_max = Column(Double, nullable=True)
    b8_median = Column(Double, nullable=True)

    # ── Vegetation Indices ────────────────────────────────────────────────
    ndvi_mean = Column(Double, nullable=True)
    ndvi_std = Column(Double, nullable=True)
    ndvi_min = Column(Double, nullable=True)
    ndvi_max = Column(Double, nullable=True)
    ndvi_median = Column(Double, nullable=True)
    ndvi_p25 = Column(Double, nullable=True)
    ndvi_p75 = Column(Double, nullable=True)

    evi_mean = Column(Double, nullable=True)
    evi_std = Column(Double, nullable=True)

    savi_mean = Column(Double, nullable=True)
    savi_std = Column(Double, nullable=True)

    msavi_mean = Column(Double, nullable=True)
    gci_mean = Column(Double, nullable=True)
    ndre_mean = Column(Double, nullable=True)

    # ── Water Indices ─────────────────────────────────────────────────────
    ndwi_mean = Column(Double, nullable=True)
    ndwi_std = Column(Double, nullable=True)
    ndwi_min = Column(Double, nullable=True)
    ndwi_max = Column(Double, nullable=True)
    ndwi_median = Column(Double, nullable=True)
    ndwi_p25 = Column(Double, nullable=True)
    ndwi_p75 = Column(Double, nullable=True)

    mndwi_mean = Column(Double, nullable=True)
    ndmi_mean = Column(Double, nullable=True)
    awei_mean = Column(Double, nullable=True)

    # ── Burn / Soil Indices ───────────────────────────────────────────────
    nbr_mean = Column(Double, nullable=True)
    nbr_std = Column(Double, nullable=True)
    nbr2_mean = Column(Double, nullable=True)
    bsi_mean = Column(Double, nullable=True)
    ndbi_mean = Column(Double, nullable=True)

    # ── GLCM Texture ─────────────────────────────────────────────────────
    glcm_contrast = Column(Double, nullable=True)
    glcm_correlation = Column(Double, nullable=True)
    glcm_energy = Column(Double, nullable=True)
    glcm_entropy = Column(Double, nullable=True)
    glcm_homogeneity = Column(Double, nullable=True)
    glcm_dissimilarity = Column(Double, nullable=True)

    # ── Spectral Summary ──────────────────────────────────────────────────
    visible_brightness = Column(Double, nullable=True)
    nir_red_difference = Column(Double, nullable=True)
    green_swir_difference = Column(Double, nullable=True)
    spectral_variance = Column(Double, nullable=True)
    spectral_entropy = Column(Double, nullable=True)

    # ── Water / Land Statistics ───────────────────────────────────────────
    water_area_sqkm = Column(Double, nullable=True)
    water_pixels = Column(Integer, nullable=True)
    vegetation_pixels = Column(Integer, nullable=True)
    soil_pixels = Column(Integer, nullable=True)
    water_percentage = Column(Double, nullable=True)
    vegetation_percentage = Column(Double, nullable=True)
    soil_percentage = Column(Double, nullable=True)
    valid_pixel_ratio = Column(Double, nullable=True)
    masked_pixel_percentage = Column(Double, nullable=True)
    water_to_land_ratio = Column(Double, nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────
    remarks = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
