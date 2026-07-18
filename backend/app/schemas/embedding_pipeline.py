"""Pydantic schemas for the embedding pipeline API endpoints."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.ML_pipeline.constants import PIPELINE_YEAR_END, PIPELINE_YEAR_START


class GenerateEmbeddingsRequest(BaseModel):
    """Request body for POST /embeddings/generate."""

    lake_ids: Optional[List[int]] = Field(
        default=None,
        description=(
            "Lake IDs to generate embeddings for. "
            "When null, all lakes with downloaded images are processed."
        ),
    )
    years: List[int] = Field(
        ...,
        min_length=1,
        description="List of years to generate embeddings for.",
    )
    confirmed: bool = Field(
        ...,
        description="Must be true to start the pipeline.",
    )

    @field_validator("years", mode="before")
    @classmethod
    def _validate_years(cls, v: list) -> list:
        for y in v:
            if not (PIPELINE_YEAR_START <= y <= PIPELINE_YEAR_END):
                raise ValueError(
                    f"Year {y} is out of range "
                    f"[{PIPELINE_YEAR_START}, {PIPELINE_YEAR_END}]."
                )
        return sorted(set(v))

    @field_validator("confirmed")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm to start embedding generation.")
        return v


class GenerateEmbeddingsResponse(BaseModel):
    """Returned immediately after triggering the embedding pipeline."""

    status: Literal["queued", "failed"]
    total_tasks: int
    message: str


class EmbeddingProgressResponse(BaseModel):
    """Real-time progress of the running (or last completed) embedding pipeline."""

    status: Literal["idle", "running", "done", "failed", "cancelled"]
    total: int
    processed: int
    success: int
    failed: int
    skipped: int
    current_lake_id: Optional[int] = None
    current_year: Optional[int] = None
    current_step: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
