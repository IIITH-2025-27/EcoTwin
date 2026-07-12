"""
ML Pipeline — three-phase ingestion orchestrator.

Phase 1 — ``ingest_region_features``
    GEE → Sentinel-2 composite → NDVI / NDWI / NBR stats
    → UPSERT sub_region_features

Phase 2 — ``compute_region_embedding``
    GEE band array → Prithvi encoder → 768-dim vector
    → UPDATE sub_regions.embedding

Phase 3 — ``classify_region``
    sub_region_features stats (+ optional embedding) → ecosystem label
    → UPDATE sub_region_features.dominant_ecosystem + ecosystem_confidence

Orchestrator — ``run_full_pipeline``
    Runs Phase 1 → Phase 2 → Phase 3 for a single (sub_region_id, year) pair.

All DB helpers use a synchronous SQLAlchemy engine because the ingestion
pipeline runs outside the API's async database session.
"""

from __future__ import annotations

from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ── Shared DB / cache helpers ──────────────────────────────────────────────────

def _sync_engine():
    """Create a fresh synchronous SQLAlchemy engine for this DB call."""
    from sqlalchemy import create_engine  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    return create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)



# ── Phase 1 ───────────────────────────────────────────────────────────────────

def ingest_region_features(
    region_id: str,
    center_lat: float,
    center_lon: float,
    year: int,
    geom_wkt: Optional[str] = None,
) -> dict:
    """
    Phase 1: fetch GEE composite → upsert sub-region features.

    Returns a result dict that is forwarded automatically to Phase 2.
    The raw band_array is included so Phase 2 does NOT need a second GEE call.
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
            geom_wkt   = geom_wkt,
        )

        _upsert_region_features(region_id, year, result.ndvi, result.ndwi, result.nbr)

        log.info("Phase 1 completed", pixel_count=result.pixel_count,
                 band_array="ok" if result.band_array is not None else "missing")
        return {
            "region_id":   region_id,
            "year":        year,
            "center_lat":  center_lat,
            "center_lon":  center_lon,
            "geom_wkt":    geom_wkt,
            "ndvi_mean":   result.ndvi.mean,
            "ndwi_mean":   result.ndwi.mean,
            "nbr_mean":    result.nbr.mean,
            "pixel_count": result.pixel_count,
            # Pass band_array to Phase 2 so GEE is only called ONCE per region/year
            "band_array":  result.band_array,
        }

    except Exception as exc:
        log.error("Phase 1 failed", error=str(exc))
        raise


# ── Phase 2 ───────────────────────────────────────────────────────────────────

def compute_region_embedding(
    phase1_result: Optional[dict] = None,
    *,
    region_id: Optional[str] = None,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    year: Optional[int] = None,
    geom_wkt: Optional[str] = None,
) -> dict:
    """
    Phase 2: Prithvi inference → upsert embedding.

    Reuses the band_array from Phase 1 when available — no second GEE call.
    Falls back to a fresh GEE fetch only when called standalone.
    """
    band_array = None
    if phase1_result is not None:
        region_id  = phase1_result["region_id"]
        center_lat = phase1_result["center_lat"]
        center_lon = phase1_result["center_lon"]
        year       = phase1_result["year"]
        geom_wkt   = phase1_result.get("geom_wkt")
        # Reuse the band_array already downloaded in Phase 1 (← no second GEE call)
        band_array = phase1_result.get("band_array")

    log = logger.bind(task="compute_embedding", region_id=region_id, year=year)
    log.info("Phase 2 started")

    try:
        from app.ML_pipeline.prithvi_inference import get_embedding  # noqa: PLC0415
        from app.core.config import settings  # noqa: PLC0415

        if band_array is None:
            # Standalone call or Phase 1 band_array was missing — fetch from GEE
            from app.ML_pipeline.gee_ingest import fetch_composite  # noqa: PLC0415
            log.info("Phase 2: fetching GEE composite (no band_array from Phase 1)")
            gee_result = fetch_composite(
                region_id  = region_id,
                center_lat = center_lat,
                center_lon = center_lon,
                year       = year,
                geom_wkt   = geom_wkt,
            )
            band_array = gee_result.band_array

        embedding = get_embedding(band_array, use_stub=settings.DEBUG)

        _upsert_region_embedding(region_id, year, embedding)

        log.info("Phase 2 completed", embedding_dim=len(embedding))
        return {
            "region_id":     region_id,
            "year":          year,
            "center_lat":    center_lat,
            "center_lon":    center_lon,
            "embedding_dim": len(embedding),
        }

    except Exception as exc:
        log.error("Phase 2 failed", error=str(exc))
        raise


# ── Phase 3 ───────────────────────────────────────────────────────────────────

def classify_region(
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

        log.info("Phase 3 completed", label=label, confidence=confidence)
        return {
            "region_id":           region_id,
            "year":                year,
            "dominant_ecosystem":  label,
            "ecosystem_confidence": confidence,
        }

    except Exception as exc:
        log.error("Phase 3 failed", error=str(exc))
        raise


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_full_pipeline(
    region_id: str,
    center_lat: float,
    center_lon: float,
    year: int,
    geom_wkt: Optional[str] = None,
) -> None:
    """
    Run Phase 1 → Phase 2 → Phase 3 for one region/year.
    """
    phase1_result = ingest_region_features(region_id, center_lat, center_lon, year, geom_wkt)
    phase2_result = compute_region_embedding(phase1_result)
    classify_region(phase2_result)
    logger.info(
        "Full pipeline completed",
        region_id=region_id,
        year=year,
    )


# ── Synchronous DB helpers ───────────────────────────────────────────────────

def _upsert_region_features(region_id, year, ndvi, ndwi, nbr) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        INSERT INTO sub_region_features (
            id, sub_region_id, year,
            ndvi_mean, ndvi_std, ndvi_median, ndvi_min, ndvi_max,
            ndwi_mean, ndwi_std, ndwi_median, ndwi_min, ndwi_max,
            nbr_mean,  nbr_std,  nbr_median,  nbr_min,  nbr_max
        ) VALUES (
            gen_random_uuid(), :sub_region_id, :year,
            :ndvi_mean, :ndvi_std, :ndvi_median, :ndvi_min, :ndvi_max,
            :ndwi_mean, :ndwi_std, :ndwi_median, :ndwi_min, :ndwi_max,
            :nbr_mean,  :nbr_std,  :nbr_median,  :nbr_min,  :nbr_max
        )
        ON CONFLICT (sub_region_id, year) DO UPDATE SET
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
            "sub_region_id": region_id, "year": year,
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
        UPDATE sub_regions
        SET embedding = '{vec_literal}'::vector, updated_at = NOW()
        WHERE sub_region_id = :sub_region_id
    """)
    with engine.begin() as conn:
        conn.execute(sql, {"sub_region_id": region_id})
    engine.dispose()


def _update_dominant_ecosystem(
    region_id: str,
    year: int,
    label: str,
    confidence: float,
) -> None:
    """
    Update dominant_ecosystem and ecosystem_confidence on the existing
    sub_region_features row.
    """
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        UPDATE sub_region_features
        SET
            dominant_ecosystem   = :label,
            ecosystem_confidence = :confidence
        WHERE sub_region_id = :sub_region_id
          AND year      = :year
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "label":      label,
            "confidence": confidence,
            "sub_region_id": region_id,
            "year":       year,
        })
    engine.dispose()


def _load_index_means(region_id: str, year: int) -> tuple[float, float, float]:
    """Load NDVI / NDWI / NBR means for the phase-3 classifier."""
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    sql = text("""
        SELECT ndvi_mean, ndwi_mean, nbr_mean
        FROM   sub_region_features
        WHERE  sub_region_id = :sub_region_id
          AND  year      = :year
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"sub_region_id": region_id, "year": year}).one()
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
        FROM   sub_regions
        WHERE  sub_region_id = :sub_region_id
          AND  year      = :year
        LIMIT 1
    """)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                sql, {"sub_region_id": region_id, "year": year}
            ).one_or_none()
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
