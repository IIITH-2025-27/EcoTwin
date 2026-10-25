"""
Local Prithvi embedding pipeline.

Processes downloaded 30 m GeoTIFFs into one embedding per lake-year: Prithvi
encodes the lake and its 500 m shore ring, the two are pooled separately and
blended into the single vector used by similarity and forecasting — without
querying Google Earth Engine.
"""

from app.embedding_pipeline.pipeline import (
    aggregate_lake_embeddings,
    cancel_embedding_pipeline,
    get_embedding_progress,
    run_embedding_pipeline,
)

__all__ = [
    "run_embedding_pipeline",
    "get_embedding_progress",
    "cancel_embedding_pipeline",
    "aggregate_lake_embeddings",
]
