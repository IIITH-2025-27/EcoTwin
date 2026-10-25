"""
Prithvi inference and lake / shore pooling.

Encodes the lake + shore tokens of each window (see ``lake_tokens``) and
pools the final-layer token embeddings into two vectors per lake-year:

  lake  = Σ lake_frac_t  · v_t / Σ lake_frac_t     → L2-normalised
  shore = Σ shore_frac_t · v_t / Σ shore_frac_t    → L2-normalised

where the fractions count valid (cloud-free) pixels only. Edge tokens that
straddle the shoreline contribute to both in proportion. The single
embedding used by similarity and forecasting is ``blend(lake, shore, w)``.

Reuses the encoder singleton from ``prithvi_inference.py`` — the model is
loaded only once per process.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import structlog

from app.embedding_pipeline.lake_tokens import LakeTokens
from app.ML_pipeline.constants import PRITHVI_EMBEDDING_DIM

logger = structlog.get_logger(__name__)


@dataclass
class LakeEmbeddingResult:
    """Pooled embeddings for one lake-year."""

    lake: np.ndarray               # (768,) L2-normalised
    shore: Optional[np.ndarray]    # (768,) L2-normalised, None if no valid shore
    combined: np.ndarray           # (768,) L2-normalised blend
    lake_weight: float             # w actually used (1.0 when shore is None)
    lake_token_weight: float       # Σ lake_frac  (≈ valid lake area in tokens)
    shore_token_weight: float      # Σ shore_frac
    tokens_encoded: int
    windows: int


def _load_encoder():
    """Reuse the same encoder singleton from prithvi_inference."""
    from app.ML_pipeline.prithvi_inference import _load_encoder  # noqa: PLC0415
    return _load_encoder()


def _l2(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm <= 1e-12:
        raise ValueError("Cannot L2-normalise a zero / non-finite vector")
    return (vec / norm).astype(np.float32)


def blend(lake: np.ndarray, shore: Optional[np.ndarray], lake_weight: float) -> np.ndarray:
    """Combined embedding: normalize(w · lake + (1 − w) · shore).

    Used both by the pipeline and by re-blending from stored parts, so the
    two always produce identical vectors. Without a shore vector the lake
    vector is returned unchanged.
    """
    if shore is None:
        return _l2(lake)
    return _l2(lake_weight * lake + (1.0 - lake_weight) * shore)


def encode_lake_tokens(tokens: LakeTokens, lake_weight: float) -> LakeEmbeddingResult:
    """Run Prithvi on every window's lake / shore tokens and pool them."""
    import torch  # noqa: PLC0415

    encoder = _load_encoder()
    device = next(encoder.parameters()).device

    lake_sum = np.zeros(PRITHVI_EMBEDDING_DIM, dtype=np.float64)
    shore_sum = np.zeros(PRITHVI_EMBEDDING_DIM, dtype=np.float64)
    lake_w = 0.0
    shore_w = 0.0
    n_tokens = 0

    with torch.no_grad():
        for w in tokens.windows:
            x = (
                torch.from_numpy(w.data)   # (C, H, W)
                .unsqueeze(0)              # (1, C, H, W)
                .unsqueeze(2)              # (1, C, T=1, H, W)
                .float()
                .to(device)
            )
            idx = torch.from_numpy(w.keep_idx).to(device)
            out = encoder.encode_tokens(x, idx).double().cpu().numpy()  # (K, D)
            if not np.isfinite(out).all():
                raise RuntimeError("Prithvi returned non-finite token embeddings")

            lake_sum += (w.lake_frac[:, None] * out).sum(axis=0)
            shore_sum += (w.shore_frac[:, None] * out).sum(axis=0)
            lake_w += float(w.lake_frac.sum())
            shore_w += float(w.shore_frac.sum())
            n_tokens += len(w.keep_idx)

    if lake_w <= 0:
        raise ValueError("No valid lake tokens to pool")

    lake = _l2(lake_sum / lake_w)
    shore = _l2(shore_sum / shore_w) if shore_w > 0 else None
    used_weight = lake_weight if shore is not None else 1.0
    combined = blend(lake, shore, lake_weight)

    logger.info(
        "Lake / shore embeddings pooled",
        windows=len(tokens.windows),
        tokens_encoded=n_tokens,
        lake_token_weight=round(lake_w, 2),
        shore_token_weight=round(shore_w, 2),
        lake_shore_cosine=(
            round(float(lake @ shore), 4) if shore is not None else None
        ),
    )
    return LakeEmbeddingResult(
        lake=lake,
        shore=shore,
        combined=combined,
        lake_weight=used_weight,
        lake_token_weight=lake_w,
        shore_token_weight=shore_w,
        tokens_encoded=n_tokens,
        windows=len(tokens.windows),
    )
