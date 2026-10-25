"""Pydantic schemas for the lake imagery download pipeline endpoints."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

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
    data_root: Optional[str] = Field(
        default=None,
        max_length=1024,
        description=(
            "Absolute directory to download every requested year into. "
            "When null, SENTINEL_DATA_DIR (backend/data/sentinel) is used."
        ),
    )
    year_roots: Optional[Dict[int, str]] = Field(
        default=None,
        description=(
            "Per-year directories ({year: path}); override data_root for "
            "those years. The paths end up in lake_images / lake_tiles."
        ),
    )

    @field_validator("year_roots")
    @classmethod
    def _validate_year_roots(cls, v: Optional[Dict[int, str]]) -> Optional[Dict[int, str]]:
        if v is None:
            return v
        for y, path in v.items():
            if not (PIPELINE_YEAR_START <= y <= PIPELINE_YEAR_END):
                raise ValueError(f"Year {y} is out of range.")
            if len(path) > 1024:
                raise ValueError(f"Path for {y} is too long.")
        return v

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
    """Real-time progress of the running (or last completed) imagery fetch.

    ``total`` / ``processed`` / ``success`` / ``failed`` / ``skipped`` count
    lake-years; ``tiles_*`` count individual tile downloads.
    """

    status: Literal["idle", "running", "cancelling", "done", "failed", "cancelled"]
    total: int
    processed: int
    success: int
    failed: int
    skipped: int
    tiles_completed: int = 0
    tiles_failed: int = 0
    active_lakes: int = 0
    current_lake_id: Optional[int] = None
    current_year: Optional[int] = None
    current_tile_index: Optional[str] = None
    year_roots: Dict[str, str] = Field(
        default_factory=dict, description="Storage root per year of this run."
    )
    errors: List[str] = Field(default_factory=list)


class StorageLocation(BaseModel):
    """A directory the imagery can be downloaded into."""

    path: str
    label: str
    free_bytes: int
    total_bytes: int


class YearRootUsage(BaseModel):
    """A storage root holding some of a year's lake images."""

    root: str
    lakes: int
    free_bytes: Optional[int] = None
    total_bytes: Optional[int] = None


class YearStorage(BaseModel):
    """Where one year's images are, read from ``lake_images``.

    ``data_root`` is where new downloads of the year go unless another
    folder is chosen: SENTINEL_DATA_DIR. ``roots`` lists where the year's
    existing images are.
    """

    year: int
    data_root: str
    is_default: bool
    free_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    roots: List[YearRootUsage] = Field(default_factory=list)


class StorageInfoResponse(BaseModel):
    """Storage location per year, free space and size estimate."""

    default_root: str
    years: List[YearStorage]
    active_lakes: int
    estimated_bytes_per_year: int = Field(
        description=(
            "Upper bound for the merged GeoTIFFs of one year (all active "
            "lakes). Tiles take about the same again until they are deleted "
            "by the merge step."
        ),
    )
    suggestions: List[StorageLocation] = Field(default_factory=list)


class StorageCheckRequest(BaseModel):
    """Request body for POST /imagery/storage/check."""

    path: str = Field(..., max_length=1024)


class StorageCheckResponse(BaseModel):
    """Result of validating a candidate storage directory."""

    path: str
    valid: bool
    error: Optional[str] = None
    free_bytes: Optional[int] = None
    total_bytes: Optional[int] = None


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


# ── Merge Tiles schemas ──────────────────────────────────────────────────


class MergeTilesRequest(BaseModel):
    """Request body for POST /imagery/merge."""

    years: List[int] = Field(
        ...,
        min_length=1,
        description="Years whose completed tiles should be merged.",
    )
    delete_tiles: bool = Field(
        default=False,
        description="Delete individual tile GeoTIFFs after a successful merge.",
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


class MergeTilesResponse(BaseModel):
    """Returned immediately after triggering the merge pipeline."""

    status: Literal["queued", "failed"]
    message: str


class MergeProgressResponse(BaseModel):
    """Real-time progress of the running (or last completed) merge."""

    status: Literal["idle", "running", "done", "failed"]
    total: int = 0
    processed: int = 0
    success: int = 0
    failed: int = 0
    current_lake_id: Optional[int] = None
    current_year: Optional[int] = None
    errors: List[str] = Field(default_factory=list)


class MergeYearOption(BaseModel):
    """A single year available for merging."""

    year: int
    lake_count: int
    output_path_pattern: str = Field(
        description="Example output path pattern for this year.",
    )


class MergeOptionsResponse(BaseModel):
    """Available years with completed tiles that can be merged."""

    years: List[MergeYearOption]
    data_root: str = Field(
        description=(
            "Default storage root. Years stored elsewhere show their own "
            "location in output_path_pattern."
        ),
    )


# Fix forward references
LakeImageStatusResponse.model_rebuild()

