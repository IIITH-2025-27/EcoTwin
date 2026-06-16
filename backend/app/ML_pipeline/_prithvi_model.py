"""
Prithvi-100M encoder interface.

This module defines ``PrithviEncoder`` — a thin wrapper used when loading
the model from a local ``.pt`` / ``.pth`` checkpoint (the
``_load_from_checkpoint`` path in prithvi_inference.py).

Architecture overview
─────────────────────
Prithvi-100M is a Vision Transformer (ViT-Large) pre-trained as a Masked
Autoencoder (MAE) on multi-temporal Sentinel-2 imagery.

    Input  : (B, T, C, H, W)  — batch × time-steps × bands × height × width
    Output : (B, num_tokens, embed_dim=768)  — patch token embeddings

The encoder patch-embeds the input, adds position + temporal embeddings,
then passes through 24 transformer blocks.  The decoder is discarded at
inference time; only the encoder trunk is needed here.

Reference implementation
────────────────────────
IBM/NASA open-source model card:
    https://huggingface.co/ibm-nasa-geospatial/Prithvi-100M

For production use, load directly from the HuggingFace hub (the default
code path in prithvi_inference.py) instead of using this stub.  This file
is only needed when you have a local checkpoint and want to instantiate the
architecture manually.

Usage
─────
    from app.ML_pipeline._prithvi_model import PrithviEncoder

    encoder = PrithviEncoder(
        img_size=224,
        num_frames=1,
        in_chans=6,
        embed_dim=768,
    )
    encoder.load_state_dict(torch.load("prithvi_100m.pt")["model"], strict=False)
    encoder.eval()

    x = torch.randn(1, 1, 6, 224, 224)   # (B, T, C, H, W)
    tokens = encoder(x)                   # (1, num_tokens, 768)
"""

from __future__ import annotations

from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class PrithviEncoder:
    """
    Minimal interface stub for the Prithvi-100M encoder trunk.

    Replace the body of ``forward()`` with the real ViT encoder from
    IBM/NASA's open-source repository when loading local weights.

    When loading from HuggingFace (the recommended path), this class is
    never instantiated — ``transformers.AutoModel.from_pretrained`` handles
    everything.
    """

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        num_frames: int = 1,
        in_chans: int = 6,
        embed_dim: int = 768,
        depth: int = 24,
        num_heads: int = 16,
        mlp_ratio: float = 4.0,
        tubelet_size: int = 1,
    ) -> None:
        self.img_size    = img_size
        self.patch_size  = patch_size
        self.num_frames  = num_frames
        self.in_chans    = in_chans
        self.embed_dim   = embed_dim
        self.depth       = depth
        self.num_heads   = num_heads
        self.mlp_ratio   = mlp_ratio
        self.tubelet_size = tubelet_size

        # Derived
        self.num_patches = (img_size // patch_size) ** 2

        try:
            self._build()
        except Exception as exc:  # torch may not be installed in non-GPU envs
            logger.warning("PrithviEncoder build skipped", error=str(exc))
            self._ready = False
        else:
            self._ready = True

    # ------------------------------------------------------------------
    # Override this method with the real ViT trunk from IBM/NASA's repo.
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """
        Instantiate the ViT trunk layers.

        ┌─────────────────────────────────────────────────────────────┐
        │  Replace this stub with the actual architecture once you    │
        │  have the IBM/NASA Prithvi source code available locally.   │
        │                                                             │
        │  The simplest approach is to install their package:         │
        │    pip install git+https://github.com/NASA-IMPACT/hls-foundation-os.git │
        │  and import ``TemporalViTEncoder`` from there.              │
        └─────────────────────────────────────────────────────────────┘
        """
        import torch.nn as nn  # noqa: PLC0415
        # Placeholder linear layer — produces correct output shape but
        # meaningless values.  Replaced by the real encoder in production.
        flat_dim = self.num_frames * self.in_chans * self.img_size * self.img_size
        self._stub_proj = nn.Linear(flat_dim, self.embed_dim)

    def forward(self, x):
        """
        Args:
            x: Tensor of shape (B, T, C, H, W).

        Returns:
            Tensor of shape (B, num_patches, embed_dim).
        """
        import torch  # noqa: PLC0415

        if not self._ready:
            # Return a zero tensor so callers can still proceed in stub mode
            B = x.shape[0]
            return torch.zeros(B, self.num_patches, self.embed_dim, device=x.device)

        B = x.shape[0]
        flat = x.reshape(B, -1)
        out = self._stub_proj(flat)                    # (B, embed_dim)
        # Expand to (B, num_patches, embed_dim) so callers can mean-pool
        return out.unsqueeze(1).expand(-1, self.num_patches, -1)

    # Make the class behave like a torch.nn.Module for load_state_dict / to()
    def load_state_dict(self, state_dict: dict, strict: bool = True):
        try:
            self._stub_proj.load_state_dict(
                {k: v for k, v in state_dict.items() if k.startswith("_stub_proj")},
                strict=False,
            )
        except Exception:
            pass  # silently ignore mismatched keys

    def eval(self):
        try:
            self._stub_proj.eval()
        except Exception:
            pass
        return self

    def to(self, device):
        try:
            self._stub_proj = self._stub_proj.to(device)
        except Exception:
            pass
        return self

    def parameters(self):
        try:
            return self._stub_proj.parameters()
        except Exception:
            return iter([])

    def __call__(self, x):
        return self.forward(x)
