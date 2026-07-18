"""
Embedding pipeline configuration.

Centralises tuneable values for the local GeoTIFF → Prithvi embedding pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.ML_pipeline.constants import (
    PRITHVI_BAND_MEAN,
    PRITHVI_BAND_STD,
    PRITHVI_EMBEDDING_DIM,
    PRITHVI_PATCH_SIZE_PX,
)


@dataclass(frozen=True)
class EmbeddingPipelineConfig:
    """Runtime configuration for the local embedding pipeline."""

    # ── Grid ──────────────────────────────────────────────────────────────
    cell_size_m: int
    min_coverage_pct: float
    projected_crs: int

    # ── Prithvi model ─────────────────────────────────────────────────────
    patch_size_px: int
    embedding_dim: int
    band_mean: list[float]
    band_std: list[float]

    # ── Processing ────────────────────────────────────────────────────────
    gpu_batch_size: int
    max_workers: int

    # ── Paths ─────────────────────────────────────────────────────────────
    data_root: Path


def get_embedding_pipeline_config() -> EmbeddingPipelineConfig:
    """Build the config from application settings + ML constants."""
    backend_root = Path(__file__).resolve().parents[2]
    data_root = Path(settings.SENTINEL_DATA_DIR)
    if not data_root.is_absolute():
        data_root = backend_root / data_root

    return EmbeddingPipelineConfig(
        cell_size_m=settings.LAKE_GRID_CELL_SIZE_METRES,
        min_coverage_pct=settings.LAKE_GRID_MIN_COVERAGE_PERCENT,
        projected_crs=6933,
        patch_size_px=PRITHVI_PATCH_SIZE_PX,
        embedding_dim=PRITHVI_EMBEDDING_DIM,
        band_mean=list(PRITHVI_BAND_MEAN),
        band_std=list(PRITHVI_BAND_STD),
        gpu_batch_size=settings.EMBEDDING_GPU_BATCH_SIZE,
        max_workers=settings.EMBEDDING_MAX_WORKERS,
        data_root=data_root,
    )
