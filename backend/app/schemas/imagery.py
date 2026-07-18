"""Pydantic schemas for the lake imagery download pipeline endpoints."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.ML_pipeline.constants import PIPELINE_YEAR_END, PIPELINE_YEAR_START


class FetchImagesRequest(BaseModel):
    """Request body for POST /imagery/fetch."""

    lake_ids: Optional[List[int]] = Field(
        default=None,
        description=(
            "Lake IDs to fetch imagery for. "
            "When null, all active lakes are processed."
        ),
    )
    years: List[int] = Field(
        ...,
        min_length=1,
        description="List of years to download Sentinel-2 composites for.",
    )
    confirmed: bool = Field(
        ...,
        description="Must be true to acknowledge the download.",
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
            raise ValueError("You must confirm to start the download.")
        return v


class FetchImagesResponse(BaseModel):
    """Returned immediately after triggering the imagery pipeline."""

    status: Literal["queued", "failed"]
    total_tasks: int
    message: str


class ImageryProgressResponse(BaseModel):
    """Real-time progress of the running (or last completed) imagery fetch."""

    status: Literal["idle", "running", "done", "failed", "cancelled"]
    total: int
    processed: int
    success: int
    failed: int
    skipped: int
    current_lake_id: Optional[int] = None
    current_year: Optional[int] = None
    current_tile_index: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class LakeTileRecord(BaseModel):
    """Single row from the lake_tiles table."""

    tile_index: str
    status: str
    image_path: Optional[str] = None
    bbox: Optional[str] = None
    file_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class LakeImageRecord(BaseModel):
    """Single row from the lake_images table."""

    year: int
    file_path: str
    status: str
    file_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class LakeImageStatusResponse(BaseModel):
    """Download status for a single lake's images, including tile details."""

    lake_id: int
    images: List[LakeImageRecord]
    tiles: List[LakeTileRecord] = Field(default_factory=list)


# Fix forward references
LakeImageStatusResponse.model_rebuild()
