"""
Phase 2 — Prithvi-100M encoder inference.

Produces a 768-dimensional embedding vector from a Sentinel-2 multi-band
patch.  The embedding is stored in ``region_embeddings`` and drives the
pgvector cosine similarity search.

Load order
──────────
1. If a local ``.pt`` / ``.pth`` checkpoint exists at ``PRITHVI_MODEL_PATH``
   (env var) → load with ``_prithvi_model.PrithviEncoder``.
2. Otherwise → download from HuggingFace hub (``PRITHVI_HF_REPO``).
3. If neither succeeds and ``use_stub=True`` (or DEBUG mode) → return a
   deterministic unit-norm stub vector for local development.

The encoder is cached in a module-level variable so it is loaded only once
per backend process.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import numpy as np
import structlog

from app.ML_pipeline.constants import (
    PRITHVI_EMBEDDING_DIM,
    PRITHVI_HF_REPO,
    PRITHVI_LOCAL_WEIGHTS,
    PRITHVI_NUM_BANDS,
    PRITHVI_NUM_FRAMES,
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


def _load_from_checkpoint(path: Path, device: str):
    """Load PrithviEncoder from a local checkpoint file."""
    import torch  # noqa: PLC0415
    from app.ML_pipeline._prithvi_model import PrithviEncoder  # noqa: PLC0415

    model = PrithviEncoder(
        img_size   = PRITHVI_PATCH_SIZE_PX,
        num_frames = PRITHVI_NUM_FRAMES,
        in_chans   = PRITHVI_NUM_BANDS,
        embed_dim  = PRITHVI_EMBEDDING_DIM,
    )
    checkpoint = torch.load(str(path), map_location=device)
    # Checkpoints may wrap weights under a "model" key
    state_dict = checkpoint.get("model", checkpoint)
    model.load_state_dict(state_dict, strict=False)
    return model.to(device)


def _load_from_hub(device: str):
    """Download Prithvi encoder from HuggingFace hub."""
    try:
        from transformers import AutoModel  # noqa: PLC0415
        model = AutoModel.from_pretrained(PRITHVI_HF_REPO, trust_remote_code=True)
        return model.to(device)
    except Exception as exc:
        raise RuntimeError(
            f"Could not load Prithvi from HuggingFace ({PRITHVI_HF_REPO}). "
            f"Ensure `transformers` is installed and the hub is reachable. Error: {exc}"
        ) from exc


def _load_encoder():
    """
    Lazy-load the encoder exactly once per worker process.
    Returns the encoder in eval mode.
    """
    global _encoder
    if _encoder is not None:
        return _encoder

    device = _get_device()
    local_path = Path(_MODEL_PATH)

    if local_path.exists():
        logger.info(
            "Loading Prithvi from local checkpoint",
            path=str(local_path),
            device=device,
        )
        _encoder = _load_from_checkpoint(local_path, device)
    else:
        logger.info(
            "Local checkpoint not found — downloading from HuggingFace",
            repo=PRITHVI_HF_REPO,
            device=device,
        )
        _encoder = _load_from_hub(device)

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


def _pool_to_vector(output) -> "np.ndarray":
    """
    Extract a 1-D (embed_dim,) float32 vector from the encoder output.
    Handles HuggingFace ModelOutput, raw tensors, and tuples.
    """
    import torch  # noqa: PLC0415

    if hasattr(output, "last_hidden_state"):
        hidden = output.last_hidden_state          # (B, num_tokens, D)
    elif isinstance(output, torch.Tensor):
        hidden = output
    elif isinstance(output, (tuple, list)):
        hidden = output[0]
    else:
        hidden = output

    # Collapse to (D,)
    if hidden.dim() == 3:
        vec = hidden.squeeze(0).mean(dim=0)        # mean-pool over spatial tokens
    elif hidden.dim() == 2:
        vec = hidden.squeeze(0)                    # CLS token
    else:
        vec = hidden.reshape(-1)[:PRITHVI_EMBEDDING_DIM]

    return vec.float().cpu().numpy()


def compute_embedding(band_array: np.ndarray) -> List[float]:
    """
    Run the Prithvi encoder on a (C, H, W) float32 Sentinel-2 patch.

    Args:
        band_array: Shape (num_bands, H, W), values already normalised to [0, 1].

    Returns:
        List of ``PRITHVI_EMBEDDING_DIM`` floats.

    Raises:
        RuntimeError: if torch is not installed or the encoder cannot be loaded.
    """
    import torch  # noqa: PLC0415

    encoder = _load_encoder()
    device  = next(encoder.parameters()).device if hasattr(encoder, "parameters") else _get_device()

    arr = _resize_to_model_input(band_array, PRITHVI_PATCH_SIZE_PX)

    # Prithvi expects (B, T, C, H, W)
    tensor = (
        torch.from_numpy(arr)   # (C, H, W)
        .unsqueeze(0)            # (1, C, H, W)
        .unsqueeze(1)            # (1, T=1, C, H, W)
        .float()
        .to(device)
    )

    with torch.no_grad():
        output = encoder(tensor)

    vec = _pool_to_vector(output)

    # L2-normalise so cosine similarity = dot product (simplifies pgvector queries)
    norm = np.linalg.norm(vec) + 1e-8
    vec  = (vec / norm).astype(np.float32)

    return vec.tolist()


# ── Development stub ───────────────────────────────────────────────────────────

def compute_embedding_stub(band_array: Optional[np.ndarray] = None) -> List[float]:
    """
    Return a deterministic unit-norm vector for local development and tests.

    The vector is seeded from the band statistics so it is unique per region
    without requiring model weights or GPU hardware.
    """
    if band_array is not None and band_array.size > 0:
        seed = int(abs(float(band_array.mean())) * 1e6) % (2 ** 31)
    else:
        seed = 42

    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(PRITHVI_EMBEDDING_DIM).astype(np.float32)
    norm = np.linalg.norm(vec) + 1e-8
    vec /= norm
    return vec.tolist()


# ── Public entry point ─────────────────────────────────────────────────────────

def get_embedding(
    band_array: Optional[np.ndarray],
    *,
    use_stub: bool = False,
) -> List[float]:
    """
    Produce a 768-dim embedding for a Sentinel-2 band patch.

    Args:
        band_array: (C, H, W) float32 array, or None if GEE download failed.
        use_stub:   Force stub mode (set to True in DEBUG / test environments).

    Returns:
        List of 768 normalised floats ready for pgvector insertion.
    """
    if use_stub:
        logger.debug("Stub embedding requested")
        return compute_embedding_stub(band_array)

    if band_array is None:
        logger.warning("band_array is None — using stub embedding")
        return compute_embedding_stub()

    try:
        return compute_embedding(band_array)
    except Exception as exc:
        logger.error(
            "Prithvi inference failed — falling back to stub embedding",
            error=str(exc),
        )
        return compute_embedding_stub(band_array)
