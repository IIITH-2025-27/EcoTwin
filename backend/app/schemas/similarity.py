from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SimilarityMethod(str, Enum):
    """
    Vector similarity / distance method used to rank analog regions.

    cosine   — 1 − (embedding <=> query)   pgvector cosine distance (<=>)
                IVFFlat index used; best for unit-norm Prithvi embeddings.
    euclidean — 1 / (1 + L2 distance)      pgvector L2 distance (<->)
                Sensitive to vector magnitude; not index-accelerated by default.
    knn      — exact k-NN inner product    pgvector inner product (<#>)
                Equivalent to cosine on L2-normalised embeddings; uses HNSW if
                available, falls back to IVFFlat.
    """
    COSINE    = "cosine"
    EUCLIDEAN = "euclidean"
    KNN       = "knn"


class AnalogResult(BaseModel):
    region_id: UUID
    center_lat: float
    center_lon: float
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    year: int
    dominant_ecosystem: Optional[str] = None


class SimilaritySearchResponse(BaseModel):
    query_region_id: UUID
    query_year: int
    analogs: List[AnalogResult]
    search_latency_ms: float
    method: SimilarityMethod = SimilarityMethod.COSINE
