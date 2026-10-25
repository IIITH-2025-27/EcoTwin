"""
Prithvi-100M encoder loader.

Holds the process-wide ``PrithviEncoder`` used by the embedding pipeline
(``app.embedding_pipeline.batch_inference``).

Load order
──────────
1. If the local Prithvi repository exists at ``PRITHVI_LOCAL_WEIGHTS``
   → load with ``_prithvi_model.PrithviEncoder``.
2. If loading fails, raise the underlying exception so the caller can
   handle the error explicitly.

The encoder is cached in a module-level variable so it is loaded only once
per backend process.
"""

from __future__ import annotations

import os

import structlog

from app.ML_pipeline.constants import PRITHVI_LOCAL_WEIGHTS

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
