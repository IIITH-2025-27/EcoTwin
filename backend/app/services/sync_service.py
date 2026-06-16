"""
Sync service — orchestrates DB wipe / backup then ML pipeline dispatch.

Wipe mode  : truncate region_features, region_embeddings, temporal_profiles,
             and region_embeddings for the requested states, then re-ingest.
Backup mode: pg_dump the full DB to /app/backups/<job_id>.dump before wiping.

Uses a synchronous SQLAlchemy engine (same pattern as report_tasks / ML pipeline
Celery tasks) so it can be called safely from the async FastAPI endpoint via
asyncio.to_thread.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from typing import List

import structlog

from app.ML_pipeline.constants import PIPELINE_QUEUE
from app.schemas.sync import (
    INDIA_STATE_CENTROIDS,
    SyncJobResponse,
    SyncMode,
    SyncRequest,
)

logger = structlog.get_logger(__name__)

# Where backups are written inside the container
BACKUP_DIR: str = os.environ.get("BACKUP_DIR", "/app/backups")

# Redis key template: stores task metadata for this job for 24 h
_SYNC_JOB_KEY = "sync_job:{job_id}"
_SYNC_JOB_TTL = 86_400  # 24 hours


# ── DB helpers ────────────────────────────────────────────────────────────────

def _sync_engine():
    from sqlalchemy import create_engine  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    return create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)


def _wipe_state_data(region_ids: List[str]) -> None:
    """
    Delete all ML-pipeline-owned rows for the given region UUIDs.
    Cascades handled by FK ON DELETE CASCADE on child tables — only
    region_features, region_embeddings, and temporal_profiles need
    explicit deletes here (reports are user data; left untouched).
    """
    if not region_ids:
        return

    from sqlalchemy import text  # noqa: PLC0415

    placeholders = ", ".join(f"'{rid}'" for rid in region_ids)
    engine = _sync_engine()
    with engine.begin() as conn:
        for table in ("region_embeddings", "temporal_profiles", "region_features"):
            conn.execute(
                text(f"DELETE FROM {table} WHERE region_id IN ({placeholders})")
            )
        # Remove the region rows themselves — all children cascade-delete
        conn.execute(
            text(f"DELETE FROM regions WHERE region_id::text IN ({placeholders})")
        )
    engine.dispose()
    logger.info("DB wipe completed", region_count=len(region_ids))


def _pg_dump(job_id: str) -> str:
    """
    Run pg_dump in Fc (custom) format and return the backup file path.
    Requires pg_dump to be on PATH (available in the postgres Docker image
    or install postgresql-client in the backend image).
    """
    from app.core.config import settings  # noqa: PLC0415

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"{job_id}.dump")

    env = os.environ.copy()
    env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

    cmd = [
        "pg_dump",
        "--format=custom",
        "--file", backup_path,
        "--host",   settings.POSTGRES_HOST,
        "--port",   str(settings.POSTGRES_PORT),
        "--username", settings.POSTGRES_USER,
        settings.POSTGRES_DB,
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    logger.info("DB backup created", path=backup_path, size_bytes=os.path.getsize(backup_path))
    return backup_path


def _ensure_region_row(region_id: str, lat: float, lon: float, state_name: str = "") -> None:
    """Insert a region row if one doesn't exist yet for this centroid."""
    from sqlalchemy import text  # noqa: PLC0415
    from app.utils.geo_utils import center_to_grid_wkt  # noqa: PLC0415

    geom_wkt = center_to_grid_wkt(lat, lon)
    engine = _sync_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO regions (region_id, center_lat, center_lon, geom, state_name)
            VALUES (:region_id, :lat, :lon, ST_GeomFromText(:wkt, 4326), :state_name)
            ON CONFLICT (region_id) DO UPDATE SET state_name = EXCLUDED.state_name
        """), {"region_id": region_id, "lat": lat, "lon": lon, "wkt": geom_wkt, "state_name": state_name})
    engine.dispose()


# ── Public service function ───────────────────────────────────────────────────

def start_sync(request: SyncRequest) -> SyncJobResponse:
    """
    Synchronous service logic — called via asyncio.to_thread from the endpoint.

    Steps:
        1. Derive stable region UUIDs from state centroids (deterministic UUIDv5).
        2. [BACKUP mode] pg_dump before any destructive operation.
        3. Wipe existing rows for the requested states.
        4. Ensure region rows exist.
        5. Dispatch one Celery chain (Phase 1 → 2 → 3) per (state × year).
        6. Return SyncJobResponse.
    """
    import hashlib  # noqa: PLC0415

    job_id = str(uuid.uuid4())
    years  = request.duration.resolved_years()
    log    = logger.bind(job_id=job_id, states=request.states, years=years)
    log.info("Sync job started", sync_mode=request.sync_mode)

    # ── 1. Derive deterministic region UUIDs from state name ──────────────
    # Using UUIDv5 (SHA-1 namespace) so the same state always maps to the
    # same UUID — idempotent across re-runs.
    state_regions: List[dict] = []
    for state in request.states:
        lat, lon = INDIA_STATE_CENTROIDS[state]
        name_bytes = state.encode()
        raw = hashlib.sha1(name_bytes).digest()[:16]
        # Manually set version=5 bits
        raw = bytearray(raw)
        raw[6] = (raw[6] & 0x0F) | 0x50
        raw[8] = (raw[8] & 0x3F) | 0x80
        region_id = str(uuid.UUID(bytes=bytes(raw)))
        state_regions.append({
            "state":     state,
            "region_id": region_id,
            "lat":       lat,
            "lon":       lon,
        })

    region_ids = [r["region_id"] for r in state_regions]

    # ── 2. Optional backup ─────────────────────────────────────────────────
    backup_path: str | None = None
    if request.sync_mode == SyncMode.BACKUP:
        try:
            backup_path = _pg_dump(job_id)
        except Exception as exc:
            log.error("Backup failed — aborting sync", error=str(exc))
            return SyncJobResponse(
                job_id           = job_id,
                status           = "failed",
                states           = request.states,
                years            = years,
                sync_mode        = request.sync_mode,
                tasks_dispatched = 0,
                message          = f"Backup failed: {exc}",
            )

    # ── 3. Wipe existing data ──────────────────────────────────────────────
    try:
        _wipe_state_data(region_ids)
    except Exception as exc:
        log.error("DB wipe failed", error=str(exc))
        return SyncJobResponse(
            job_id           = job_id,
            status           = "failed",
            states           = request.states,
            years            = years,
            sync_mode        = request.sync_mode,
            tasks_dispatched = 0,
            message          = f"DB wipe failed: {exc}",
        )

    # ── 4. Ensure region rows exist ────────────────────────────────────────
    for r in state_regions:
        try:
            _ensure_region_row(r["region_id"], r["lat"], r["lon"], r["state"])
        except Exception as exc:
            log.warning("Could not create region row", state=r["state"], error=str(exc))

    # ── 5. Dispatch Celery chains ──────────────────────────────────────────
    from app.ML_pipeline.pipeline import run_full_pipeline_task  # noqa: PLC0415

    tasks_dispatched = 0
    # task_meta: list of dicts stored in Redis for the status endpoint
    task_meta: List[dict] = []
    for r in state_regions:
        for year in years:
            try:
                async_result = run_full_pipeline_task.apply_async(
                    args=[r["region_id"], r["lat"], r["lon"], year],
                    queue=PIPELINE_QUEUE,
                )
                tasks_dispatched += 1
                task_meta.append({
                    "task_id":   async_result.id,
                    "state":     r["state"],
                    "region_id": r["region_id"],
                    "year":      year,
                })
            except Exception as exc:
                log.warning(
                    "Task dispatch failed",
                    state=r["state"],
                    year=year,
                    error=str(exc),
                )

    # ── 5b. Persist task metadata in Redis ────────────────────────────────
    _store_job_meta(job_id, request.states, years, task_meta)

    log.info("Sync job dispatched", tasks_dispatched=tasks_dispatched)

    return SyncJobResponse(
        job_id           = job_id,
        status           = "queued",
        states           = request.states,
        years            = years,
        sync_mode        = request.sync_mode,
        tasks_dispatched = tasks_dispatched,
        backup_path      = backup_path,
        message          = (
            f"Pipeline started for {len(request.states)} state(s) "
            f"× {len(years)} year(s) = {tasks_dispatched} task(s) dispatched."
        ),
    )


# ── Redis helpers (synchronous — called from Celery-context or to_thread) ─────

def _redis_sync_client():
    """Return a synchronous redis client."""
    import redis  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    return redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, decode_responses=True)


def _store_job_meta(
    job_id: str,
    states: List[str],
    years: List[int],
    task_meta: List[dict],
) -> None:
    """Persist job → task mapping in Redis so the status endpoint can query it."""
    payload = json.dumps({
        "states":     states,
        "years":      years,
        "task_meta":  task_meta,   # [{task_id, state, region_id, year}, ...]
    })
    try:
        r = _redis_sync_client()
        r.setex(_SYNC_JOB_KEY.format(job_id=job_id), _SYNC_JOB_TTL, payload)
        r.close()
    except Exception as exc:
        logger.warning("Could not store job meta in Redis", job_id=job_id, error=str(exc))


# ── Status query (called via asyncio.to_thread) ───────────────────────────────

# Celery task states we surface to the frontend
_CELERY_STATE_MAP = {
    "PENDING":  "pending",
    "RECEIVED": "pending",
    "STARTED":  "running",
    "RETRY":    "running",
    "SUCCESS":  "success",
    "FAILURE":  "failed",
    "REVOKED":  "failed",
}


def get_job_status(job_id: str) -> dict:
    """
    Read stored task IDs from Redis, query Celery result backend for each,
    and return an aggregated status dict.

    Returns:
        {
          "job_id": str,
          "states": [...],
          "years":  [...],
          "overall": "pending" | "running" | "success" | "failed" | "partial",
          "total":   int,
          "counts":  {"pending": int, "running": int, "success": int, "failed": int},
          "tasks":   [{"task_id", "state", "year", "status", "error"}, ...]
        }
    """
    try:
        r = _redis_sync_client()
        raw = r.get(_SYNC_JOB_KEY.format(job_id=job_id))
        r.close()
    except Exception as exc:
        return {"error": f"Redis unavailable: {exc}"}

    if raw is None:
        return {"error": "Job not found (expired or never started)"}

    data       = json.loads(raw)
    task_meta  = data.get("task_meta", [])
    states_val = data.get("states", [])
    years_val  = data.get("years", [])

    from celery.result import AsyncResult  # noqa: PLC0415
    from app.workers.celery_app import celery_app  # noqa: PLC0415

    tasks_out = []
    counts    = {"pending": 0, "running": 0, "success": 0, "failed": 0}

    for meta in task_meta:
        tid = meta["task_id"]
        try:
            result = AsyncResult(tid, app=celery_app)
            celery_state = result.state          # str like "PENDING", "SUCCESS" …
            status = _CELERY_STATE_MAP.get(celery_state, "pending")
            error  = str(result.info) if status == "failed" and result.info else None
        except Exception:
            status = "pending"
            error  = None

        counts[status] = counts.get(status, 0) + 1
        tasks_out.append({
            "task_id":   tid,
            "state":     meta["state"],
            "year":      meta["year"],
            "status":    status,
            "error":     error,
        })

    total = len(tasks_out)
    if total == 0:
        overall = "pending"
    elif counts["success"] == total:
        overall = "success"
    elif counts["failed"] == total:
        overall = "failed"
    elif counts["failed"] > 0 and counts["pending"] == 0 and counts["running"] == 0:
        overall = "partial"
    elif counts["running"] > 0 or counts["success"] > 0:
        overall = "running"
    else:
        overall = "pending"

    return {
        "job_id":   job_id,
        "states":   states_val,
        "years":    years_val,
        "overall":  overall,
        "total":    total,
        "counts":   counts,
        "tasks":    tasks_out,
    }

