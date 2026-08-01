"""Pydantic schemas for the lake feature extraction API endpoints."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class GenerateLakeFeaturesRequest(BaseModel):
    """Request body for POST /lake-features/generate."""

    year: Optional[int] = Field(
        default=None,
        description=(
            "Year to process. When null, all merged images across "
            "all years are processed."
        ),
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "When true, re-compute and overwrite existing feature rows. "
            "When false, skip lakes that already have completed features."
        ),
    )


class GenerateLakeFeaturesResponse(BaseModel):
    """Returned immediately after triggering the feature generation pipeline."""

    status: Literal["queued", "failed"]
    message: str
    total: int = 0


class LakeFeatureProgressResponse(BaseModel):
    """Real-time progress of the running (or last completed) feature pipeline."""

    status: Literal["idle", "running", "done", "failed"]
    total: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    current_lake_id: Optional[int] = None
    current_year: Optional[int] = None
    errors: List[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
    processing_rate: float = Field(
        default=0.0, description="Lakes processed per second"
    )
    estimated_remaining_seconds: float = 0.0
    estimated_completion_time: Optional[str] = None


class GenerateLakeFeaturesResult(BaseModel):
    """Final result returned after the pipeline completes (used internally)."""

    total: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
