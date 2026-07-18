"""
Coverage-weighted mean pooling for lake-level embeddings.

Aggregates per-cell embeddings into a single lake embedding using
the lake coverage ratio of each cell as its weight.
"""

from __future__ import annotations

from typing import List

import numpy as np
import structlog

from app.ML_pipeline.constants import PRITHVI_EMBEDDING_DIM

logger = structlog.get_logger(__name__)


def weighted_mean_pool(
    embeddings: List[np.ndarray],
    weights: List[float],
) -> np.ndarray:
    """
    Compute a coverage-weighted mean of cell embeddings.

    Args:
        embeddings: List of (768,) float32 L2-normalised vectors.
        weights:    List of coverage percentages (0–100) corresponding
                    to each embedding.

    Returns:
        (768,) float32 L2-normalised aggregated embedding.

    Raises:
        ValueError: if inputs are empty or mismatched in length.
    """
    if not embeddings or not weights:
        raise ValueError("Cannot pool empty embeddings or weights")
    if len(embeddings) != len(weights):
        raise ValueError(
            f"Length mismatch: {len(embeddings)} embeddings vs {len(weights)} weights"
        )

    # Filter out zero embeddings and non-positive weights
    valid_pairs = [
        (emb, w)
        for emb, w in zip(embeddings, weights)
        if w > 0 and np.any(emb != 0) and emb.shape == (PRITHVI_EMBEDDING_DIM,)
    ]

    if not valid_pairs:
        logger.warning("No valid embeddings for pooling — returning zero vector")
        return np.zeros(PRITHVI_EMBEDDING_DIM, dtype=np.float32)

    valid_embs, valid_weights = zip(*valid_pairs)

    # Stack and compute weighted mean
    emb_matrix = np.stack(valid_embs, axis=0)       # (N, 768)
    w_array = np.array(valid_weights, dtype=np.float32)  # (N,)
    w_sum = w_array.sum()

    if w_sum <= 0:
        logger.warning("Weight sum is zero — returning unweighted mean")
        pooled = emb_matrix.mean(axis=0)
    else:
        # Weighted mean: sum(w_i * e_i) / sum(w_i)
        pooled = (emb_matrix * w_array[:, np.newaxis]).sum(axis=0) / w_sum

    # L2 normalise the result
    norm = np.linalg.norm(pooled) + 1e-8
    pooled = (pooled / norm).astype(np.float32)

    # Final validation
    if not np.isfinite(pooled).all():
        logger.error("Pooled embedding contains NaN/Inf — returning zero vector")
        return np.zeros(PRITHVI_EMBEDDING_DIM, dtype=np.float32)

    logger.info(
        "Weighted mean pooling completed",
        num_cells=len(valid_pairs),
        total_weight=float(w_sum),
    )
    return pooled
