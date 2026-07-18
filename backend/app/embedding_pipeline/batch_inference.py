"""
GPU-batched Prithvi inference for grid cells.

Processes multiple (C, H, W) arrays in a single forward pass to
maximise GPU utilisation.  Reuses the model singleton from
``prithvi_inference.py`` — the encoder is loaded only once per process.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import structlog

from app.ML_pipeline.constants import PRITHVI_EMBEDDING_DIM, PRITHVI_PATCH_SIZE_PX

logger = structlog.get_logger(__name__)


def _get_device() -> str:
    try:
        import torch  # noqa: PLC0415
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _load_encoder():
    """Reuse the same encoder singleton from prithvi_inference."""
    from app.ML_pipeline.prithvi_inference import _load_encoder  # noqa: PLC0415
    return _load_encoder()


def compute_embeddings_batch(
    cell_arrays: List[np.ndarray],
) -> List[np.ndarray]:
    """
    Run Prithvi inference on a batch of cell arrays.

    Args:
        cell_arrays: List of (C, H, W) float32 arrays, each already
                     normalised and resized to PRITHVI_PATCH_SIZE_PX.

    Returns:
        List of (768,) float32 L2-normalised embedding vectors.
        Returns empty array for cells that fail inference.
    """
    import torch  # noqa: PLC0415

    if not cell_arrays:
        return []

    encoder = _load_encoder()
    device = next(encoder.parameters()).device if hasattr(encoder, "parameters") else _get_device()

    batch_size = len(cell_arrays)
    logger.info("Batch inference started", batch_size=batch_size, device=str(device))

    # ── Stack into batch tensor ──────────────────────────────────────────
    # Each array: (C, H, W) → target (B, C, T=1, H, W)
    tensors = []
    for arr in cell_arrays:
        # Ensure correct spatial size
        if arr.shape[1] != PRITHVI_PATCH_SIZE_PX or arr.shape[2] != PRITHVI_PATCH_SIZE_PX:
            arr = _resize_array(arr, PRITHVI_PATCH_SIZE_PX)
        tensors.append(torch.from_numpy(arr).float())

    batch = torch.stack(tensors, dim=0)      # (B, C, H, W)
    batch = batch.unsqueeze(2)                # (B, C, T=1, H, W)
    batch = batch.to(device)

    # ── Forward pass ─────────────────────────────────────────────────────
    with torch.no_grad():
        output = encoder(batch)

    # ── Extract embeddings ───────────────────────────────────────────────
    # encoder returns (hidden_states, mask, ids_restore)
    if isinstance(output, (tuple, list)):
        hidden = output[0]
    elif isinstance(output, torch.Tensor):
        hidden = output
    elif hasattr(output, "last_hidden_state"):
        hidden = output.last_hidden_state
    else:
        hidden = output

    # hidden shape: (B, 1+num_spatial_tokens, D)
    # Skip CLS token at index 0, mean-pool spatial tokens
    embeddings: List[np.ndarray] = []

    for i in range(batch_size):
        try:
            if hidden.dim() == 3:
                spatial_tokens = hidden[i, 1:, :]     # (num_tokens, D)
                vec = spatial_tokens.mean(dim=0)       # (D,)
            elif hidden.dim() == 2:
                vec = hidden[i]
            else:
                vec = hidden[i].reshape(-1)[:PRITHVI_EMBEDDING_DIM]

            vec = vec.float().cpu().numpy()

            # Validate
            if vec.size != PRITHVI_EMBEDDING_DIM or not np.isfinite(vec).all():
                logger.warning("Invalid embedding for cell", cell_idx=i)
                embeddings.append(np.zeros(PRITHVI_EMBEDDING_DIM, dtype=np.float32))
                continue

            # L2 normalise
            norm = np.linalg.norm(vec) + 1e-8
            vec = (vec / norm).astype(np.float32)

            embeddings.append(vec)

        except Exception as exc:
            logger.warning("Embedding extraction failed", cell_idx=i, error=str(exc))
            embeddings.append(np.zeros(PRITHVI_EMBEDDING_DIM, dtype=np.float32))

    logger.info(
        "Batch inference completed",
        batch_size=batch_size,
        valid_embeddings=sum(1 for e in embeddings if np.any(e != 0)),
    )
    return embeddings


def _resize_array(arr: np.ndarray, target: int) -> np.ndarray:
    """Resize (C, H, W) to (C, target, target)."""
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
        c, h, w = arr.shape
        out = np.zeros((c, target, target), dtype=arr.dtype)
        ch, cw = min(h, target), min(w, target)
        out[:, :ch, :cw] = arr[:, :ch, :cw]
        return out
