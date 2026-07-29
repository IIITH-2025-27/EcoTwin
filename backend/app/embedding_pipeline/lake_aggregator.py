"""
Lake-level embedding aggregation.

Aggregates per-cell (sub_region) embeddings into exactly ONE lake-level
embedding per (lake_id, year) using coverage-weighted mean pooling
followed by L2 normalisation.

Can be used as:
  1. A library – call ``aggregate_all_lake_embeddings()`` from application code.
  2. A CLI script – ``python -m app.embedding_pipeline.lake_aggregator [options]``.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from typing import Dict, List, Optional

import numpy as np
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.embedding_pipeline.weighted_pooling import weighted_mean_pool
from app.ML_pipeline.constants import PRITHVI_EMBEDDING_DIM

logger = structlog.get_logger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────


@dataclasses.dataclass
class LakeYearResult:
    """Outcome for a single (lake_id, year) aggregation."""

    lake_id: int
    year: int
    status: str  # "success" | "skipped" | "failed"
    reason: str = ""
    num_cells: int = 0
    total_weight: float = 0.0
    elapsed_ms: float = 0.0


@dataclasses.dataclass
class BatchResult:
    """Summary of a full batch aggregation run."""

    success: List[LakeYearResult] = dataclasses.field(default_factory=list)
    skipped: List[LakeYearResult] = dataclasses.field(default_factory=list)
    failed: List[LakeYearResult] = dataclasses.field(default_factory=list)

    @property
    def summary(self) -> Dict:
        return {
            "success": len(self.success),
            "skipped": len(self.skipped),
            "failed": len(self.failed),
            "total": len(self.success) + len(self.skipped) + len(self.failed),
        }


# ── Database helpers ──────────────────────────────────────────────────────


def _sync_engine():
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def _discover_lake_year_pairs(
    engine,
    lake_ids: Optional[List[int]] = None,
    years: Optional[List[int]] = None,
) -> List[tuple]:
    """
    Return all distinct (lake_id, year) pairs that have at least one
    completed sub_region embedding.
    """
    conditions = [
        "status = 'completed'",
        "embedding IS NOT NULL",
    ]
    params: Dict = {}

    if lake_ids:
        conditions.append("lake_id = ANY(:lake_ids)")
        params["lake_ids"] = lake_ids
    if years:
        conditions.append("year = ANY(:years)")
        params["years"] = years

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT DISTINCT lake_id, year
        FROM sub_regions
        WHERE {where}
        ORDER BY lake_id, year
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [(row[0], row[1]) for row in rows]


def _fetch_cell_embeddings(
    session, lake_id: int, year: int
) -> List[tuple]:
    """
    Fetch all completed cell embeddings and their coverage_percent for a
    given (lake_id, year).

    Returns list of (embedding_array, coverage_percent) tuples.
    Only rows with status='completed', non-NULL embedding, and
    coverage_percent > 0 are returned.
    """
    sql = text("""
        SELECT embedding::text, coverage_percent, cell_number
        FROM sub_regions
        WHERE lake_id = :lake_id
          AND year    = :year
          AND status  = 'completed'
          AND embedding IS NOT NULL
          AND coverage_percent > 0
        ORDER BY cell_number
    """)

    rows = session.execute(sql, {"lake_id": lake_id, "year": year}).fetchall()

    results: List[tuple] = []
    for raw_vec, cov, cell_num in rows:
        try:
            floats = [float(x) for x in raw_vec.strip("[]").split(",")]
            arr = np.array(floats, dtype=np.float32)
            if arr.shape != (PRITHVI_EMBEDDING_DIM,):
                logger.warning(
                    "Wrong embedding dimension — skipping cell",
                    lake_id=lake_id, year=year, cell_number=cell_num,
                    expected=PRITHVI_EMBEDDING_DIM, got=arr.shape,
                )
                continue
            if not np.isfinite(arr).all():
                logger.warning(
                    "Embedding contains NaN/Inf — skipping cell",
                    lake_id=lake_id, year=year, cell_number=cell_num,
                )
                continue
            if np.all(arr == 0):
                logger.warning(
                    "Zero embedding — skipping cell",
                    lake_id=lake_id, year=year, cell_number=cell_num,
                )
                continue
            results.append((arr, float(cov)))
        except Exception as exc:
            logger.warning(
                "Malformed embedding row — skipping",
                lake_id=lake_id, year=year, cell_number=cell_num,
                error=str(exc)[:200],
            )
            continue

    return results


def _upsert_lake_embedding(
    session,
    lake_id: int,
    year: int,
    embedding: np.ndarray,
) -> None:
    """
    Insert or update the aggregated lake-level embedding in the regions table.

    The aggregated embedding is stored on the lake/region row for the
    matching lake and year so it is available from the same table used by
    downstream region-based workflows.
    """
    vec_literal = "[" + ",".join(str(float(v)) for v in embedding) + "]"

    sql = text("""
        INSERT INTO regions (
            region_id, lake_id, year, center_lat, center_lon,
            embedding, status, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), lake.lake_id, :year,
            COALESCE(ST_Y(lake.centroid), ST_Y(ST_Centroid(lake.geom)), lake.pour_lat, 0),
            COALESCE(ST_X(lake.centroid), ST_X(ST_Centroid(lake.geom)), lake.pour_long, 0),
            CAST(:embedding AS vector),
            'completed',
            NOW(), NOW()
        FROM lakes AS lake
        WHERE lake.lake_id = :lake_id
        ON CONFLICT ON CONSTRAINT uq_regions_lake_year DO UPDATE SET
            embedding       = EXCLUDED.embedding,
            status          = 'completed',
            error_message   = NULL,
            center_lat      = EXCLUDED.center_lat,
            center_lon      = EXCLUDED.center_lon,
            updated_at      = NOW()
    """)

    result = session.execute(sql, {
        "lake_id": lake_id,
        "year": year,
        "embedding": vec_literal,
    })
    if result.rowcount != 1:
        raise ValueError(f"Lake {lake_id} was not found")


# ── Core aggregation ─────────────────────────────────────────────────────


def aggregate_single_lake_year(
    session,
    lake_id: int,
    year: int,
) -> LakeYearResult:
    """
    Compute a single lake-level embedding for one (lake_id, year).

    Steps:
        1. Fetch all completed cell embeddings + coverage_percent.
        2. Use coverage_percent as the weight for each cell.
        3. Compute coverage-weighted mean across all cells.
        4. L2-normalise the result.
        5. Upsert into lake_embeddings.

    Returns a LakeYearResult with status, reason, and metadata.
    """
    t0 = time.perf_counter()
    log = logger.bind(lake_id=lake_id, year=year)

    try:
        # 1. Fetch cell embeddings
        pairs = _fetch_cell_embeddings(session, lake_id, year)

        if not pairs:
            elapsed = (time.perf_counter() - t0) * 1000
            log.info("No valid cell embeddings — skipping")
            return LakeYearResult(
                lake_id=lake_id, year=year,
                status="skipped",
                reason="No completed cell embeddings with valid embedding and coverage > 0",
                elapsed_ms=elapsed,
            )

        embeddings = [emb for emb, _ in pairs]
        weights = [cov for _, cov in pairs]
        total_weight = float(sum(weights))

        # 2. Weighted mean pooling (includes L2 normalisation)
        pooled = weighted_mean_pool(embeddings, weights)

        # 3. Validate result
        if not np.any(pooled != 0):
            elapsed = (time.perf_counter() - t0) * 1000
            log.warning("Weighted pooling returned zero vector")
            return LakeYearResult(
                lake_id=lake_id, year=year,
                status="failed",
                reason="Weighted pooling returned zero vector (all embeddings may be invalid)",
                num_cells=len(pairs),
                total_weight=sum(weights),
                elapsed_ms=elapsed,
            )

        if not np.isfinite(pooled).all():
            elapsed = (time.perf_counter() - t0) * 1000
            log.error("Pooled embedding contains NaN/Inf")
            return LakeYearResult(
                lake_id=lake_id, year=year,
                status="failed",
                reason="Pooled embedding contains NaN/Inf values",
                num_cells=len(pairs),
                total_weight=sum(weights),
                elapsed_ms=elapsed,
            )

        # 4. Upsert into regions
        _upsert_lake_embedding(
            session,
            lake_id,
            year,
            pooled,
        )
        session.commit()

        elapsed = (time.perf_counter() - t0) * 1000
        log.info(
            "✓ Lake embedding aggregated",
            num_cells=len(pairs),
            total_weight=round(sum(weights), 2),
            elapsed_ms=round(elapsed, 1),
        )
        return LakeYearResult(
            lake_id=lake_id, year=year,
            status="success",
            num_cells=len(pairs),
            total_weight=sum(weights),
            elapsed_ms=elapsed,
        )

    except Exception as exc:
        session.rollback()
        elapsed = (time.perf_counter() - t0) * 1000
        error_msg = str(exc)[:500]
        log.error("✗ Lake embedding aggregation failed", error=error_msg)
        return LakeYearResult(
            lake_id=lake_id, year=year,
            status="failed",
            reason=error_msg,
            elapsed_ms=elapsed,
        )


# ── Batch aggregation ────────────────────────────────────────────────────


def aggregate_all_lake_embeddings(
    lake_ids: Optional[List[int]] = None,
    years: Optional[List[int]] = None,
) -> BatchResult:
    """
    Batch-aggregate cell-level embeddings into lake-level embeddings for
    all discovered (lake_id, year) pairs.

    For each pair:
        - Fetches completed sub_region embeddings.
        - Computes coverage-weighted mean.
        - L2-normalises the result.
        - Upserts into lake_embeddings.
        - Logs success / skipped / failed with reason.

    Args:
        lake_ids: Restrict to these lakes. None = all with data.
        years:    Restrict to these years.  None = all with data.

    Returns:
        BatchResult with per-pair outcomes and summary counts.
    """
    engine = _sync_engine()
    Session = sessionmaker(bind=engine)
    result = BatchResult()

    try:
        pairs = _discover_lake_year_pairs(engine, lake_ids, years)

        if not pairs:
            logger.info("No (lake_id, year) pairs found for aggregation")
            return result

        logger.info(
            "Lake embedding batch aggregation started",
            total_pairs=len(pairs),
            lake_ids=lake_ids,
            years=years,
        )

        t_batch = time.perf_counter()

        for lake_id, year in pairs:
            with Session() as session:
                r = aggregate_single_lake_year(session, lake_id, year)

            if r.status == "success":
                result.success.append(r)
            elif r.status == "skipped":
                result.skipped.append(r)
            else:
                result.failed.append(r)

        batch_elapsed = time.perf_counter() - t_batch
        summary = result.summary

        logger.info(
            "Lake embedding batch aggregation finished",
            **summary,
            elapsed_sec=round(batch_elapsed, 2),
        )

        # Log details for skipped and failed
        for r in result.skipped:
            logger.info(
                "  SKIPPED",
                lake_id=r.lake_id, year=r.year, reason=r.reason,
            )
        for r in result.failed:
            logger.warning(
                "  FAILED",
                lake_id=r.lake_id, year=r.year, reason=r.reason,
            )

        return result

    finally:
        engine.dispose()


# ── CLI entry point ───────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate sub-region embeddings into lake-level embeddings."
    )
    parser.add_argument(
        "--lake-ids",
        type=int,
        nargs="*",
        default=None,
        help="Specific lake IDs to process (default: all with data).",
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="*",
        default=None,
        help="Specific years to process (default: all with data).",
    )
    args = parser.parse_args()

    structlog.configure(
        processors=[
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    result = aggregate_all_lake_embeddings(
        lake_ids=args.lake_ids,
        years=args.years,
    )

    summary = result.summary
    print(f"\n{'='*60}")
    print(f"  Lake Embedding Aggregation Report")
    print(f"{'='*60}")
    print(f"  Total pairs processed : {summary['total']}")
    print(f"  Successful            : {summary['success']}")
    print(f"  Skipped               : {summary['skipped']}")
    print(f"  Failed                : {summary['failed']}")
    print(f"{'='*60}")

    if result.success:
        print(f"\n  ✓ Successfully aggregated:")
        for r in result.success:
            print(
                f"    lake_id={r.lake_id:>8}, year={r.year}, "
                f"cells={r.num_cells:>4}, weight={r.total_weight:>8.2f}, "
                f"time={r.elapsed_ms:.0f}ms"
            )

    if result.skipped:
        print(f"\n  ○ Skipped:")
        for r in result.skipped:
            print(f"    lake_id={r.lake_id:>8}, year={r.year}: {r.reason}")

    if result.failed:
        print(f"\n  ✗ Failed:")
        for r in result.failed:
            print(f"    lake_id={r.lake_id:>8}, year={r.year}: {r.reason}")

    print()

    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
