"""
Phase 2 — Prithvi-100M encoder inference.

Produces a 768-dimensional embedding vector from a Sentinel-2 multi-band
patch. The embedding is stored in ``sub_regions.embedding`` and drives the
pgvector cosine similarity search.

Load order
──────────
1. If the local Prithvi repository exists at ``PRITHVI_LOCAL_WEIGHTS``
   → load with ``_prithvi_model.PrithviEncoder``.
2. If loading or inference fails, raise the underlying exception so the
   caller can handle the error explicitly.

The encoder is cached in a module-level variable so it is loaded only once
per backend process.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import List, Optional

import numpy as np
import structlog

from app.ML_pipeline.constants import (
    PRITHVI_EMBEDDING_DIM,
    PRITHVI_LOCAL_WEIGHTS,
    PRITHVI_PATCH_SIZE_PX,
)

logger = structlog.get_logger(__name__)

# Runtime model path: env var overrides the constant default
_MODEL_PATH: str = os.environ.get("PRITHVI_MODEL_PATH", PRITHVI_LOCAL_WEIGHTS)

# Module-level singleton — loaded once per worker process, never reloaded
_encoder = None


# ── Encoder loading ────────────────────────────────────────────────────────────

def _get_device() -> str:
    try:
        import torch  # noqa: PLC0415
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _load_encoder():
    """
    Lazy-load the encoder exactly once per worker process.
    Returns the encoder in eval mode.
    """
    global _encoder
    if _encoder is not None:
        return _encoder

    device = _get_device()

    logger.info(
        "Loading Prithvi from local repository",
        path=_MODEL_PATH,
        device=device,
    )

    from app.ML_pipeline._prithvi_model import PrithviEncoder  # noqa: PLC0415

    _encoder = PrithviEncoder(model_name_or_path=_MODEL_PATH)
    _encoder = _encoder.to(device)
    _encoder.eval()
    logger.info("Prithvi encoder ready", device=device)
    return _encoder


# ── Inference ──────────────────────────────────────────────────────────────────

def _resize_to_model_input(arr: np.ndarray, target: int) -> np.ndarray:
    """
    Resize a (C, H, W) array to (C, target, target).
    Uses OpenCV bilinear when available; falls back to a simple crop/pad.
    """
    if arr.shape[1] == target and arr.shape[2] == target:
        return arr

    try:
        import cv2  # noqa: PLC0415
        return np.stack(
            [cv2.resize(arr[c], (target, target), interpolation=cv2.INTER_LINEAR)
             for c in range(arr.shape[0])],
            axis=0,
        )
    except ImportError:
        # Crop or zero-pad without adding a dependency
        c, h, w = arr.shape
        out = np.zeros((c, target, target), dtype=arr.dtype)
        ch, cw = min(h, target), min(w, target)
        out[:, :ch, :cw] = arr[:, :ch, :cw]
        return out


def _is_valid_embedding(vec) -> bool:
    if vec is None:
        return False
    try:
        array = np.asarray(vec, dtype=np.float32).reshape(-1)
    except Exception:
        return False
    return array.size == PRITHVI_EMBEDDING_DIM and np.isfinite(array).all()


def _pool_to_vector(encoder_output) -> "np.ndarray":
    """
    Extract a 1-D (embed_dim,) float32 vector from the PrithviViT encoder.

    The encoder returns (hidden_states, mask, ids_restore).
    hidden_states shape: (B, 1+num_tokens, D)  — index 0 is CLS token.
    We skip CLS and mean-pool the spatial tokens.
    """
    import torch  # noqa: PLC0415

    # encoder.forward() returns (hidden_states, mask, ids_restore)
    if isinstance(encoder_output, (tuple, list)):
        hidden = encoder_output[0]
    elif isinstance(encoder_output, torch.Tensor):
        hidden = encoder_output
    elif hasattr(encoder_output, "last_hidden_state"):
        hidden = encoder_output.last_hidden_state
    else:
        hidden = encoder_output

    # hidden shape: (B, 1+num_spatial_tokens, D)
    # Skip CLS token at index 0 and mean-pool spatial tokens
    if hidden.dim() == 3:
        spatial_tokens = hidden[:, 1:, :]          # skip CLS → (B, num_tokens, D)
        vec = spatial_tokens.squeeze(0).mean(dim=0) # mean-pool → (D,)
    elif hidden.dim() == 2:
        vec = hidden.squeeze(0)
    else:
        vec = hidden.reshape(-1)[:PRITHVI_EMBEDDING_DIM]

    return vec.float().cpu().numpy()


def _validate_embedding_array(embedding: object) -> np.ndarray:
    """Ensure embeddings are finite, one-dimensional, and match the expected size."""
    arr = np.asarray(embedding, dtype=np.float32)
    if arr.ndim != 1:
        raise ValueError(f"Embedding must be 1-D, got shape {arr.shape}")
    if arr.size != PRITHVI_EMBEDDING_DIM:
        raise ValueError(f"Embedding size mismatch: expected {PRITHVI_EMBEDDING_DIM}, got {arr.size}")
    if not np.isfinite(arr).all():
        raise ValueError("Embedding contains NaN/Inf values")
    return arr


def compute_embedding(band_array: np.ndarray) -> List[float]:
    """
    Run the Prithvi encoder on a (C, H, W) float32 Sentinel-2 patch.

    Args:
        band_array: Shape (num_bands, H, W), already normalised per-band
                    using the Prithvi training mean/std.

    Returns:
        List of ``PRITHVI_EMBEDDING_DIM`` floats.

    Raises:
        RuntimeError: if torch is not installed or the encoder cannot be loaded.
    """
    import torch  # noqa: PLC0415

    encoder = _load_encoder()
    device  = next(encoder.parameters()).device if hasattr(encoder, "parameters") else _get_device()

    arr = _resize_to_model_input(band_array, PRITHVI_PATCH_SIZE_PX)

    # PrithviViT PatchEmbed expects (B, C, T, H, W)
    tensor = (
        torch.from_numpy(arr)   # (C, H, W)
        .unsqueeze(0)            # (1, C, H, W)
        .unsqueeze(2)            # (1, C, T=1, H, W)
        .float()
        .to(device)
    )

    with torch.no_grad():
        output = encoder(tensor)

    vec = _pool_to_vector(output)
    if not _is_valid_embedding(vec):
        raise RuntimeError("Prithvi returned an invalid embedding")

    # L2-normalise so cosine similarity = dot product (simplifies pgvector queries)
    norm = np.linalg.norm(vec) + 1e-8
    if not np.isfinite(norm) or norm <= 0:
        raise RuntimeError("Prithvi returned a zero-norm embedding")
    vec = (vec / norm).astype(np.float32)
    if not _is_valid_embedding(vec):
        raise RuntimeError("Prithvi embedding became invalid after normalization")

    return vec.tolist()


# ── Public entry point ─────────────────────────────────────────────────────────

def _check_sync_cancelled() -> None:
    from app.services import sync_service  # noqa: PLC0415

    if sync_service.is_sync_cancelled():
        raise RuntimeError("Sync cancelled")


def get_embedding(
    band_array: Optional[np.ndarray],
    *,
    use_stub: bool = False,
) -> List[float]:
    """
    Produce a 768-dim embedding for a Sentinel-2 band patch.

    Args:
        band_array: (C, H, W) float32 array, or None if GEE download failed.
        use_stub: Retained for compatibility; ignored because no stub fallback is used.

    Returns:
        List of 768 normalised floats ready for pgvector insertion.

    Raises:
        ValueError: if ``band_array`` is missing/invalid.
        RuntimeError: if Prithvi inference fails.
    """
    if band_array is None:
        raise ValueError("band_array is required for Prithvi embedding")

    _check_sync_cancelled()
    embedding = compute_embedding(band_array)
    _check_sync_cancelled()
    validated = _validate_embedding_array(embedding)
    logger.info(
        "Embedding ready for persistence",
        embedding_dim=int(validated.size),
        embedding_preview=validated[:8].tolist(),
    )
    return validated.tolist()
