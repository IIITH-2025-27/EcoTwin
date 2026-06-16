"""
Pydantic schemas for the data-sync pipeline endpoint.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.ML_pipeline.constants import (
    PIPELINE_BATCH_SIZE,
    PIPELINE_YEAR_END,
    PIPELINE_YEAR_START,
)


class SyncMode(str, Enum):
    """How the sync should handle existing data."""
    WIPE = "wipe"      # truncate all ML-pipeline tables then ingest fresh
    BACKUP = "backup"  # pg_dump to /app/backups/ then wipe + ingest


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


# ── Central bounding boxes for each Indian state (lat, lon of centroid) ───────
# Used by the pipeline to seed region rows if they don't already exist.
INDIA_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Andhra Pradesh":         (15.9129,  79.7400),
    "Arunachal Pradesh":      (28.2180,  94.7278),
    "Assam":                  (26.2006,  92.9376),
    "Bihar":                  (25.0961,  85.3131),
    "Chhattisgarh":           (21.2787,  81.8661),
    "Goa":                    (15.2993,  74.1240),
    "Gujarat":                (22.2587,  71.1924),
    "Haryana":                (29.0588,  76.0856),
    "Himachal Pradesh":       (31.1048,  77.1734),
    "Jharkhand":              (23.6102,  85.2799),
    "Karnataka":              (15.3173,  75.7139),
    "Kerala":                 (10.8505,  76.2711),
    "Madhya Pradesh":         (22.9734,  78.6569),
    "Maharashtra":            (19.7515,  75.7139),
    "Manipur":                (24.6637,  93.9063),
    "Meghalaya":              (25.4670,  91.3662),
    "Mizoram":                (23.1645,  92.9376),
    "Nagaland":               (26.1584,  94.5624),
    "Odisha":                 (20.9517,  85.0985),
    "Punjab":                 (31.1471,  75.3412),
    "Rajasthan":              (27.0238,  74.2179),
    "Sikkim":                 (27.5330,  88.5122),
    "Tamil Nadu":             (11.1271,  78.6569),
    "Telangana":              (18.1124,  79.0193),
    "Tripura":                (23.9408,  91.9882),
    "Uttar Pradesh":          (26.8467,  80.9462),
    "Uttarakhand":            (30.0668,  79.0193),
    "West Bengal":            (22.9868,  87.8550),
    "Andaman and Nicobar":    (11.7401,  92.6586),
    "Chandigarh":             (30.7333,  76.7794),
    "Dadra and Nagar Haveli": (20.1809,  73.0169),
    "Daman and Diu":          (20.4283,  72.8397),
    "Delhi":                  (28.7041,  77.1025),
    "Jammu and Kashmir":      (33.7782,  76.5762),
    "Ladakh":                 (34.1526,  77.5770),
    "Lakshadweep":            (10.5667,  72.6417),
    "Puducherry":             (11.9416,  79.8083),
}

MAX_STATES_PER_SYNC: int = 3   # hard limit enforced on both frontend and backend


class SyncRequest(BaseModel):
    """Request body for POST /sync/start."""

    states: List[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_STATES_PER_SYNC,
        description="Indian state / UT names. Maximum 3.",
    )
    duration: SyncDuration
    sync_mode: SyncMode = SyncMode.WIPE
    # Set by frontend when user explicitly accepted the warning dialog
    confirmed: bool = Field(
        ...,
        description="Must be True — confirms the user acknowledged the data-loss warning.",
    )

    @field_validator("states")
    @classmethod
    def _validate_state_names(cls, v: List[str]) -> List[str]:
        unknown = [s for s in v if s not in INDIA_STATE_CENTROIDS]
        if unknown:
            raise ValueError(f"Unknown state(s): {unknown}")
        if len(v) > MAX_STATES_PER_SYNC:
            raise ValueError(f"Maximum {MAX_STATES_PER_SYNC} states allowed per sync.")
        return v

    @field_validator("confirmed")
    @classmethod
    def _must_be_confirmed(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm the data-loss warning to proceed.")
        return v


class SyncJobResponse(BaseModel):
    """Returned immediately after the sync is triggered."""

    job_id: str
    status: Literal["queued", "failed"]
    states: List[str]
    years: List[int]
    sync_mode: SyncMode
    tasks_dispatched: int
    message: str
    backup_path: Optional[str] = None
