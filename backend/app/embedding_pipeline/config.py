"""
Embedding pipeline configuration.

Centralises tuneable values for the local GeoTIFF → Prithvi embedding pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.ML_pipeline.constants import (
    PRITHVI_BAND_MEAN,
    PRITHVI_BAND_STD,
    PRITHVI_EMBEDDING_DIM,
    PRITHVI_PATCH_SIZE_PX,
    PRITHVI_TOKEN_PX,
)


@dataclass(frozen=True)
class EmbeddingPipelineConfig:
    """Runtime configuration for the local embedding pipeline."""

    # ── Lake / shore regions ──────────────────────────────────────────────
    shore_ring_m: int
    lake_weight: float
    min_lake_pixels: int
    projected_crs: int

    # ── Prithvi model ─────────────────────────────────────────────────────
    window_px: int
    token_px: int
    embedding_dim: int
    band_mean: list[float]
    band_std: list[float]


def get_embedding_pipeline_config() -> EmbeddingPipelineConfig:
    """Build the config from application settings + ML constants."""
    if not 0.0 <= settings.EMBEDDING_LAKE_WEIGHT <= 1.0:
        raise ValueError("EMBEDDING_LAKE_WEIGHT must be within [0, 1]")

    return EmbeddingPipelineConfig(
        shore_ring_m=settings.EMBEDDING_SHORE_RING_METRES,
        lake_weight=settings.EMBEDDING_LAKE_WEIGHT,
        min_lake_pixels=settings.EMBEDDING_MIN_LAKE_PIXELS,
        projected_crs=6933,
        window_px=PRITHVI_PATCH_SIZE_PX,
        token_px=PRITHVI_TOKEN_PX,
        embedding_dim=PRITHVI_EMBEDDING_DIM,
        band_mean=list(PRITHVI_BAND_MEAN),
        band_std=list(PRITHVI_BAND_STD),
    )
