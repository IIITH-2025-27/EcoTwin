"""
ML Pipeline Celery tasks — three-phase ingestion orchestrator.

Phase 1 — ``ingest_region_features_task``
    GEE → Sentinel-2 composite → NDVI / NDWI / NBR stats
    → UPSERT region_features + temporal_profiles

Phase 2 — ``compute_region_embedding_task``
    GEE band array → Prithvi encoder → 768-dim vector
    → UPSERT region_embeddings
    → Invalidate Redis similarity / forecast cache

Phase 3 — ``classify_region_task``
    region_features stats (+ optional embedding) → ecosystem label
    → UPDATE region_features.dominant_ecosystem + ecosystem_confidence
    → Invalidate Redis cache

Orchestrator — ``run_full_pipeline_task``
    Dispatches a Celery chain: Phase 1 → Phase 2 → Phase 3 for a single
    (region_id, year) pair.  Use this from management scripts or Celery beat.

All DB helpers use a synchronous SQLAlchemy engine (same pattern as
report_tasks.py) because Celery workers run in separate OS processes, not
async event loops.
"""

from __future__ import annotations

from typing import Optional

import structlog

from app.workers.celery_app import celery_app
from app.ML_pipeline.constants import (
    PIPELINE_MAX_RETRIES,
    PIPELINE_QUEUE,
    PIPELINE_RETRY_DELAY_SEC,
)

logger = structlog.get_logger(__name__)


# ── Shared DB / cache helpers ──────────────────────────────────────────────────

def _sync_engine():
    """Create a fresh synchronous SQLAlchemy engine for this DB call."""
    from sqlalchemy import create_engine  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    return create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)


def _invalidate_redis_for_region(region_id: str) -> None:
    """
    Synchronously remove all cached similarity and forecast keys for the
    region.  Non-fatal: a warning is logged and the pipeline continues.
    """
    try:
        import redis as sync_redis  # noqa: PLC0415
        from app.core.config import settings  # noqa: PLC0415

        client = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        keys = (
            client.keys(f"similarity:{region_id}:*")
            + client.keys(f"forecast:{region_id}")
        )
        if keys:
            client.delete(*keys)
            logger.info(
                "Redis cache invalidated",
                region_id=region_id,
                keys_deleted=len(keys),
            )
        client.close()
    except Exception as exc:
        logger.warning(
            "Redis invalidation failed (non-fatal)",
            region_id=region_id,
            error=str(exc),
        )


# ── Phase 1 ───────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.ML_pipeline.pipeline.ingest_region_features_task",
    bind=True,
    max_retries=PIPELINE_MAX_RETRIES,
    default_retry_delay=PIPELINE_RETRY_DELAY_SEC,
    acks_late=True,
    queue=PIPELINE_QUEUE,
)
def ingest_region_features_task(
    self,
    region_id: str,
    center_lat: float,
    center_lon: float,
    year: int,
) -> dict:
    """
    Phase 1: fetch GEE composite → upsert region_features + temporal_profiles.

    Returns a result dict that is forwarded automatically to Phase 2 when
    tasks are chained with ``.s()``.
    """
    log = logger.bind(task="ingest_features", region_id=region_id, year=year)
    log.info("Phase 1 started")

    try:
        from app.ML_pipeline.gee_ingest import fetch_composite  # noqa: PLC0415

        result = fetch_composite(
            region_id  = region_id,
            center_lat = center_lat,
            center_lon = center_lon,
            year       = year,
        )

        _upsert_region_features(region_id, year, result.ndvi, result.ndwi, result.nbr)
        _upsert_temporal_profile(
            region_id,
            year,
            ndvi_mean = result.ndvi.mean,
            ndwi_mean = result.ndwi.mean,
            nbr_mean  = result.nbr.mean,
        )

        log.info("Phase 1 completed", pixel_count=result.pixel_count)
        return {
            "region_id":  region_id,
            "year":       year,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "ndvi_mean":  result.ndvi.mean,
            "ndwi_mean":  result.ndwi.mean,
            "nbr_mean":   result.nbr.mean,
            "pixel_count": result.pixel_count,
        }

    except Exception as exc:
        log.error("Phase 1 failed", error=str(exc))
        raise self.retry(exc=exc)


# ── Phase 2 ───────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.ML_pipeline.pipeline.compute_region_embedding_task",
    bind=True,
    max_retries=PIPELINE_MAX_RETRIES,
    default_retry_delay=PIPELINE_RETRY_DELAY_SEC,
    acks_late=True,
    queue=PIPELINE_QUEUE,
)
def compute_region_embedding_task(
    self,
    phase1_result: Optional[dict] = None,
    *,
    region_id: Optional[str] = None,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    year: Optional[int] = None,
) -> dict:
    """
    Phase 2: download GEE band array → Prithvi inference → upsert embedding.

    Can be called standalone (pass keyword args) or chained from Phase 1
    (``phase1_result`` received automatically as positional arg).
    """
    # Support Celery chain: phase1_result is the first positional arg
    if phase1_result is not None:
        region_id  = phase1_result["region_id"]
        center_lat = phase1_result["center_lat"]
        center_lon = phase1_result["center_lon"]
        year       = phase1_result["year"]

    log = logger.bind(task="compute_embedding", region_id=region_id, year=year)
    log.info("Phase 2 started")

    try:
        from app.ML_pipeline.gee_ingest import fetch_composite  # noqa: PLC0415
        from app.ML_pipeline.prithvi_inference import get_embedding  # noqa: PLC0415
        from app.core.config import settings  # noqa: PLC0415

        gee_result = fetch_composite(
            region_id  = region_id,
            center_lat = center_lat,
            center_lon = center_lon,
            year       = year,
        )

        # Use stub embeddings in DEBUG / development mode to skip GPU requirement
        embedding = get_embedding(gee_result.band_array, use_stub=settings.DEBUG)

        _upsert_region_embedding(region_id, year, embedding)
        _invalidate_redis_for_region(region_id)

        log.info("Phase 2 completed", embedding_dim=len(embedding))
        return {
            "region_id":   region_id,
            "year":        year,
            "center_lat":  center_lat,
            "center_lon":  center_lon,
            "embedding_dim": len(embedding),
        }

    except Exception as exc:
        log.error("Phase 2 failed", error=str(exc))
        raise self.retry(exc=exc)


# ── Phase 3 ───────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.ML_pipeline.pipeline.classify_region_task",
    bind=True,
    max_retries=PIPELINE_MAX_RETRIES,
    default_retry_delay=PIPELINE_RETRY_DELAY_SEC,
    acks_late=True,
    queue=PIPELINE_QUEUE,
)
def classify_region_task(
    self,
    phase2_result: Optional[dict] = None,
    *,
    region_id: Optional[str] = None,
    year: Optional[int] = None,
) -> dict:
    """
    Phase 3: classify ecosystem from index means → update dominant_ecosystem.

    Chained from Phase 2 or callable standalone.
    """
    if phase2_result is not None:
        region_id = phase2_result["region_id"]
        year      = phase2_result["year"]

    log = logger.bind(task="classify_region", region_id=region_id, year=year)
    log.info("Phase 3 started")

    try:
        from app.ML_pipeline.classifier import classify_region  # noqa: PLC0415

        ndvi_mean, ndwi_mean, nbr_mean = _load_index_means(region_id, year)

        # Optionally load the embedding for Stage B (learned model)
        embedding = _load_embedding_vector(region_id, year)

        label, confidence = classify_region(ndvi_mean, ndwi_mean, nbr_mean, embedding)

        _update_dominant_ecosystem(region_id, year, label, confidence)
        _invalidate_redis_for_region(region_id)

        log.info("Phase 3 completed", label=label, confidence=confidence)
        return {
            "region_id":           region_id,
            "year":                year,
            "dominant_ecosystem":  label,
            "ecosystem_confidence": confidence,
        }

    except Exception as exc:
        log.error("Phase 3 failed", error=str(exc))
        raise self.retry(exc=exc)


# ── Orchestrator ───────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.ML_pipeline.pipeline.run_full_pipeline_task",
    queue=PIPELINE_QUEUE,
)
def run_full_pipeline_task(
    region_id: str,
    center_lat: float,
    center_lon: float,
    year: int,
) -> None:
    """
    Dispatch Phase 1 → Phase 2 → Phase 3 as a Celery chain for one region/year.

    Use this task from management scripts or Celery beat for bulk ingestion.
    Each phase receives the previous phase's return dict automatically.

    Example (from a management script)::

        from app.ML_pipeline.pipeline import run_full_pipeline_task
        run_full_pipeline_task.delay(region_id, lat, lon, year)
    """
    from celery import chain  # noqa: PLC0415

    pipeline_chain = chain(
        ingest_region_features_task.s(region_id, center_lat, center_lon, year),
        compute_region_embedding_task.s(),
        classify_region_task.s(),
    )
    pipeline_chain.apply_async()
    logger.info(
        "Full pipeline chain dispatched",
        region_id=region_id,
        year=year,
    )


# ── Synchronous DB helpers (Celery worker context) ────────────────────────────

def _upsert_region_features(region_id, year, ndvi, ndwi, nbr) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        INSERT INTO region_features (
            id, region_id, year,
            ndvi_mean, ndvi_std, ndvi_median, ndvi_min, ndvi_max,
            ndwi_mean, ndwi_std, ndwi_median, ndwi_min, ndwi_max,
            nbr_mean,  nbr_std,  nbr_median,  nbr_min,  nbr_max
        ) VALUES (
            gen_random_uuid(), :region_id, :year,
            :ndvi_mean, :ndvi_std, :ndvi_median, :ndvi_min, :ndvi_max,
            :ndwi_mean, :ndwi_std, :ndwi_median, :ndwi_min, :ndwi_max,
            :nbr_mean,  :nbr_std,  :nbr_median,  :nbr_min,  :nbr_max
        )
        ON CONFLICT (region_id, year) DO UPDATE SET
            ndvi_mean   = EXCLUDED.ndvi_mean,
            ndvi_std    = EXCLUDED.ndvi_std,
            ndvi_median = EXCLUDED.ndvi_median,
            ndvi_min    = EXCLUDED.ndvi_min,
            ndvi_max    = EXCLUDED.ndvi_max,
            ndwi_mean   = EXCLUDED.ndwi_mean,
            ndwi_std    = EXCLUDED.ndwi_std,
            ndwi_median = EXCLUDED.ndwi_median,
            ndwi_min    = EXCLUDED.ndwi_min,
            ndwi_max    = EXCLUDED.ndwi_max,
            nbr_mean    = EXCLUDED.nbr_mean,
            nbr_std     = EXCLUDED.nbr_std,
            nbr_median  = EXCLUDED.nbr_median,
            nbr_min     = EXCLUDED.nbr_min,
            nbr_max     = EXCLUDED.nbr_max
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "region_id":   region_id, "year": year,
            "ndvi_mean":   ndvi.mean,   "ndvi_std":  ndvi.std,
            "ndvi_median": ndvi.median, "ndvi_min":  ndvi.min,  "ndvi_max": ndvi.max,
            "ndwi_mean":   ndwi.mean,   "ndwi_std":  ndwi.std,
            "ndwi_median": ndwi.median, "ndwi_min":  ndwi.min,  "ndwi_max": ndwi.max,
            "nbr_mean":    nbr.mean,    "nbr_std":   nbr.std,
            "nbr_median":  nbr.median,  "nbr_min":   nbr.min,   "nbr_max":  nbr.max,
        })
    engine.dispose()


def _upsert_temporal_profile(
    region_id: str,
    year: int,
    ndvi_mean: float,
    ndwi_mean: float,
    nbr_mean: float,
) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        INSERT INTO temporal_profiles (id, region_id, year, ndvi, ndwi, nbr)
        VALUES (gen_random_uuid(), :region_id, :year, :ndvi, :ndwi, :nbr)
        ON CONFLICT (region_id, year) DO UPDATE SET
            ndvi = EXCLUDED.ndvi,
            ndwi = EXCLUDED.ndwi,
            nbr  = EXCLUDED.nbr
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "region_id": region_id,
            "year":      year,
            "ndvi":      ndvi_mean,
            "ndwi":      ndwi_mean,
            "nbr":       nbr_mean,
        })
    engine.dispose()


def _upsert_region_embedding(
    region_id: str,
    year: int,
    embedding: list,
) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    # Build the pgvector literal inline (same approach as EmbeddingRepository)
    vec_literal = "[" + ",".join(map(str, embedding)) + "]"
    sql = text(f"""
        INSERT INTO region_embeddings (id, region_id, year, embedding)
        VALUES (gen_random_uuid(), :region_id, :year, '{vec_literal}'::vector)
        ON CONFLICT (region_id, year) DO UPDATE SET
            embedding = EXCLUDED.embedding
    """)
    with engine.begin() as conn:
        conn.execute(sql, {"region_id": region_id, "year": year})
    engine.dispose()


def _update_dominant_ecosystem(
    region_id: str,
    year: int,
    label: str,
    confidence: float,
) -> None:
    """
    Update dominant_ecosystem and ecosystem_confidence on the existing
    region_features row.  Requires migration 002_add_ecosystem_confidence.
    """
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        UPDATE region_features
        SET
            dominant_ecosystem   = :label,
            ecosystem_confidence = :confidence
        WHERE region_id = :region_id
          AND year      = :year
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "label":      label,
            "confidence": confidence,
            "region_id":  region_id,
            "year":       year,
        })
    engine.dispose()


def _load_index_means(region_id: str, year: int) -> tuple[float, float, float]:
    """Load NDVI / NDWI / NBR means for the phase-3 classifier."""
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        SELECT ndvi_mean, ndwi_mean, nbr_mean
        FROM   region_features
        WHERE  region_id = :region_id
          AND  year      = :year
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"region_id": region_id, "year": year}).one()
    engine.dispose()
    return (
        float(row.ndvi_mean or 0.0),
        float(row.ndwi_mean or 0.0),
        float(row.nbr_mean  or 0.0),
    )


def _load_embedding_vector(region_id: str, year: int) -> Optional[list]:
    """
    Load the stored embedding for Phase 3 (Stage B classifier).
    Returns None when the embedding row does not yet exist.
    """
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        SELECT embedding::text
        FROM   region_embeddings
        WHERE  region_id = :region_id
          AND  year      = :year
        LIMIT 1
    """)
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"region_id": region_id, "year": year}).one_or_none()
        if row is None:
            return None
        # pgvector returns the vector as a string like "[0.1,0.2,...]"
        raw = str(row[0]).strip("[]")
        return [float(v) for v in raw.split(",")]
    except Exception as exc:
        logger.debug("Could not load embedding vector", error=str(exc))
        return None
    finally:
        engine.dispose()
