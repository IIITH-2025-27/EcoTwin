"""
Local Prithvi embedding pipeline.

Processes downloaded GeoTIFFs through grid generation, cell extraction,
GPU-batched inference, and weighted mean pooling to produce per-cell
and per-lake embeddings — without querying Google Earth Engine.
"""

from app.embedding_pipeline.pipeline import (
    cancel_embedding_pipeline,
    get_embedding_progress,
    run_embedding_pipeline,
)

__all__ = [
    "run_embedding_pipeline",
    "get_embedding_progress",
    "cancel_embedding_pipeline",
]
