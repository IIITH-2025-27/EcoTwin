"""
Pydantic schemas for the data-sync pipeline endpoint.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.ML_pipeline.constants import (
    PIPELINE_BATCH_SIZE,
    PIPELINE_YEAR_END,
    PIPELINE_YEAR_START,
)


class SyncMode(str, Enum):
    """How the sync should handle existing data."""
    REFRESH = "refresh"
    BACKUP = "backup"


class SyncSource(str, Enum):
    HYDROLAKES = "hydrolakes"
    STORED_REGIONS = "stored_regions"


class DurationUnit(str, Enum):
    MONTHS = "months"
    YEARS  = "years"


class SyncDuration(BaseModel):
    """User-supplied time range.  Either a single year or a month/year duration."""
    mode: Literal["year", "duration"]

    # ── Single-year mode ──────────────────────────────────────────
    year: Optional[int] = Field(
        default=None,
        ge=PIPELINE_YEAR_START,
        le=PIPELINE_YEAR_END,
        description="Four-digit year (used when mode='year').",
    )

    # ── Duration mode ─────────────────────────────────────────────
    start_year:  Optional[int] = Field(default=None, ge=PIPELINE_YEAR_START, le=PIPELINE_YEAR_END)
    start_month: Optional[int] = Field(default=None, ge=1, le=12)
    end_year:    Optional[int] = Field(default=None, ge=PIPELINE_YEAR_START, le=PIPELINE_YEAR_END)
    end_month:   Optional[int] = Field(default=None, ge=1, le=12)

    @field_validator("year", mode="before")
    @classmethod
    def _check_year_present_when_year_mode(cls, v, info):
        if info.data.get("mode") == "year" and v is None:
            raise ValueError("year is required when mode='year'")
        return v

    def resolved_years(self) -> List[int]:
        """Return the list of distinct calendar years covered by this duration."""
        if self.mode == "year":
            return [self.year]
        start = self.start_year or PIPELINE_YEAR_START
        end   = self.end_year   or PIPELINE_YEAR_END
        return list(range(start, end + 1))


class SyncRequest(BaseModel):
    """Request body for POST /sync/start."""

    source_type: SyncSource = Field(
        default=SyncSource.HYDROLAKES,
        description="Where to read regions from: HydroLAKES boundaries or stored regions.",
    )
    country: str = Field(
        default="India",
        min_length=1,
        description="Country whose lake regions should be synchronized.",
    )
    region_ids: Optional[List[str]] = Field(
        default=None,
        description="Selected stored region IDs when source_type='stored_regions'.",
    )
    states: Optional[List[str]] = Field(
        default=None,
        description="If set, only lakes whose state field matches one of these values are processed.",
    )
    duration: SyncDuration
    sync_mode: SyncMode = SyncMode.REFRESH
    confirmed: bool = Field(
        ...,
        description="Must be True — confirms the user acknowledged the data-loss warning.",
    )

    @field_validator("country")
    @classmethod
    def _validate_country(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("country must not be empty")
        return v.strip()

    @field_validator("confirmed")
    @classmethod
    def _must_be_confirmed(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm the data-loss warning to proceed.")
        return v

    @model_validator(mode="after")
    def _validate_source_selection(self) -> "SyncRequest":
        if self.source_type == SyncSource.STORED_REGIONS and not self.region_ids:
            raise ValueError("region_ids are required when source_type='stored_regions'")
        return self


class HydroLakeBoundaryResponse(BaseModel):
    hydrolake_id: str
    name: str
    country: str
    center_lat: float
    center_lon: float
    area_sqkm: float
    bbox: Optional[List[float]] = None
    geometry: Optional[dict] = None


class LakeImportResponse(BaseModel):
    source_path: str
    country: str
    total_records: int
    inserted_records: int
    updated_records: int
    skipped_records: int
    message: str


class IndiaStateImportResponse(BaseModel):
    source_path: str
    states_stored: int
    lakes_updated: int


class SyncJobResponse(BaseModel):
    """Returned immediately after the sync is triggered."""

    job_id: str
    status: Literal["queued", "failed", "completed", "cancelled"]
    source_type: SyncSource
    country: str
    region_ids: List[str]
    years: List[int]
    sync_mode: SyncMode
    tasks_dispatched: int
    total_regions: int
    inserted_regions: int
    updated_regions: int
    skipped_regions: int
    message: str
    backup_path: Optional[str] = None
