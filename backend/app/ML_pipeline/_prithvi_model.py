"""
Prithvi-100M encoder interface.

This module defines ``PrithviEncoder`` — a wrapper around the locally cloned
PrithviMAE model at ``PRITHVI_LOCAL_WEIGHTS``.

Loading follows the official Prithvi inference.py pattern:
    1. Read ``config.json`` → extract ``pretrained_cfg``
    2. Instantiate ``PrithviMAE(**cfg)``
    3. ``torch.load(checkpoint.pt)`` → discard ``pos_embed`` → ``load_state_dict``

Architecture overview
─────────────────────
Prithvi-100M is a ViT pre-trained as a Masked Autoencoder on Sentinel-2.

    Input  : (B, C, T, H, W)  — batch × bands × time-steps × height × width
    Output : (B, 1+num_tokens, 768)  — CLS + spatial patch embeddings

We call the encoder with ``mask_ratio=0.0`` so every token is kept.

Usage
─────
    from app.ML_pipeline._prithvi_model import PrithviEncoder

    encoder = PrithviEncoder()
    encoder.eval()

    x = torch.randn(1, 6, 1, 224, 224)   # (B, C, T, H, W)
    hidden, mask, ids = encoder(x)        # hidden: (1, 1+196, 768)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_LOCAL_MODEL_DIR = "local_prithvi_model"  # relative to backend/app/ML_pipeline
DEFAULT_CHECKPOINT_NAME = "Prithvi_EO_V1_100M.pt"


class PrithviEncoder:
    """Wrapper around the locally cloned PrithviMAE repository."""

    def __init__(
        self,
        model_name_or_path: str | None = None,
    ) -> None:
        self.model_name_or_path = model_name_or_path or os.environ.get(
            "PRITHVI_MODEL_PATH",
            DEFAULT_LOCAL_MODEL_DIR,
        )
        self._backbone = None  # PrithviMAE instance
        self._encoder = None   # PrithviViT (encoder only)
        self._ready = False
        self._build()

    def _build(self) -> None:
        import torch  # noqa: PLC0415

        model_dir = Path(self.model_name_or_path)
        if not model_dir.exists():
            msg = f"Prithvi model directory not found: {model_dir}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        # ── 1. Read config.json to get model params ─────────────────────
        config_path = model_dir / "config.json"
        if not config_path.exists():
            msg = f"config.json not found in {model_dir}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        with open(config_path, "r") as f:
            config = json.load(f)["pretrained_cfg"]

        logger.info(
            "Loaded config from prithvi model",
            path=str(config_path),
            embed_dim=config.get("embed_dim"),
            depth=config.get("depth"),
            num_heads=config.get("num_heads"),
        )

        # ── 2. Add repo to sys.path and import PrithviMAE ───────────────
        repo_str = str(model_dir)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        from prithvi_mae import PrithviMAE  # noqa: PLC0415

        # Override num_frames for single-timestep inference
        config["num_frames"] = 1
        config["in_chans"] = config.get("in_chans", 6)

        # Remove non-model keys that PrithviMAE.__init__ doesn't accept
        for key in ["bands", "mean", "std", "origin_url", "paper_ids", "mask_ratio"]:
            config.pop(key, None)

        logger.info("Instantiating PrithviMAE", config=config)
        self._backbone = PrithviMAE(**config)

        # ── 3. Load checkpoint weights ──────────────────────────────────
        checkpoint_path = model_dir / DEFAULT_CHECKPOINT_NAME
        if not checkpoint_path.exists():
            # Try alternate name
            checkpoint_path = model_dir / "Prithvi_100M.pt"
        if not checkpoint_path.exists():
            msg = f"No .pt checkpoint found in {model_dir}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        state_dict = torch.load(str(checkpoint_path), map_location=device, weights_only=False)

        # Discard pos_embed keys — they are recomputed from the grid size
        for k in list(state_dict.keys()):
            if "pos_embed" in k:
                del state_dict[k]

        self._backbone.load_state_dict(state_dict, strict=False)
        self._encoder = self._backbone.encoder
        self._ready = True

        total_params = sum(p.numel() for p in self._backbone.parameters())
        logger.info(
            "PrithviMAE loaded",
            checkpoint=str(checkpoint_path),
            params=total_params,
            device=device,
        )
        logger.info("PrithviMAE loaded successfully",
                     checkpoint=str(checkpoint_path), params=total_params)

    def forward(self, x):
        """Run encoder forward pass with mask_ratio=0.0 (keep all tokens).

        Args:
            x: Tensor of shape (B, C, T, H, W).

        Returns:
            Tuple (hidden_states, mask, ids_restore) where hidden_states
            has shape (B, 1+num_tokens, embed_dim).
        """
        if not self._ready:
            msg = "PrithviEncoder was not built successfully"
            logger.error(msg)
            raise RuntimeError(msg)
        return self._encoder(x, mask_ratio=0.0)

    def eval(self):
        if self._backbone is not None:
            self._backbone.eval()
        return self

    def to(self, device):
        if self._backbone is not None:
            self._backbone = self._backbone.to(device)
            self._encoder = self._backbone.encoder
        return self

    def parameters(self):
        if self._backbone is None:
            return iter(())
        return self._backbone.parameters()

    def __call__(self, x):
        return self.forward(x)
