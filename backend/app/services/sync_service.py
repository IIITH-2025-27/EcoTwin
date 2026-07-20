"""Sync service for importing lake regions and starting downstream processing."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import unicodedata
import uuid
from pathlib import Path
from typing import List

import structlog
from shapely import wkt as shapely_wkt
from shapely.geometry import shape

from app.core.config import settings
from app.schemas.sync import (
    HydroLakeBoundaryResponse,
    SyncJobResponse,
    SyncMode,
    SyncRequest,
    SyncSource,
)

logger = structlog.get_logger(__name__)

APP_DIR = Path(__file__).resolve().parents[1]

BACKUP_DIR: str = os.environ.get("BACKUP_DIR", "/app/backups")
HYDROLAKES_SOURCE_PATH: str = settings.HYDROLAKES_SOURCE_PATH
HYDROLAKES_SHAPEFILE_PATH: str = (
    settings.HYDROLAKES_SHAPEFILE_PATH
    or str(APP_DIR / "datasets" / "HydroLAKES_polys_v10_shp" / "HydroLAKES_polys_v10_shp" / "HydroLAKES_polys_v10.shp")
)
INDIA_STATES_SOURCE_PATH: str = settings.INDIA_STATES_SOURCE_PATH

# ── Single global sync progress (no job IDs needed) ────────────────────────
# Shape: {status, total_lakes, processed, success, failed, current_lake, current_year, errors}
_SYNC_PROGRESS: dict = {
    "status": "idle",          # idle | running | done | failed
    "total_lakes": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "current_lake": None,
    "current_year": None,
    "errors": [],
}
_SYNC_LOCK = threading.Lock()
_ACTIVE_SYNC_JOBS: dict[str, dict] = {}

LAKE_IMPORT_BATCH_SIZE = 250
# ``shapeName`` is the field used by geoBoundaries ADM1 GeoJSON files.
INDIA_STATE_NAME_FIELDS = (
    "state_name",
    "state",
    "st_nm",
    "name_1",
    "name",
    "shapename",
)


def _normalize_lake_label(value: object) -> str:
    """Convert accented Latin characters in source labels to their plain form.

    Boundary data can spell names such as ``Bihār`` with a macron.  Lake
    display names are intended for the English UI, so persist the plain form
    (``Bihar``) instead.
    """
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", str(value).strip())
        if not unicodedata.combining(character)
    )


def _sync_engine():
    from sqlalchemy import create_engine  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    return create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)


def _wipe_country_data(country: str) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM regions WHERE lower(country) = lower(:country)"),
            {"country": country},
        )
    engine.dispose()
    logger.info("Country lake regions wiped", country=country)


def _pg_dump(job_id: str) -> str:
    from app.core.config import settings  # noqa: PLC0415

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"{job_id}.dump")

    env = os.environ.copy()
    env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

    cmd = [
        "pg_dump",
        "--format=custom",
        "--file",
        backup_path,
        "--host",
        settings.POSTGRES_HOST,
        "--port",
        str(settings.POSTGRES_PORT),
        "--username",
        settings.POSTGRES_USER,
        settings.POSTGRES_DB,
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    logger.info("DB backup created", path=backup_path, size_bytes=os.path.getsize(backup_path))
    return backup_path


def _load_lake_records(country: str) -> list[dict]:
    source_path = HYDROLAKES_SOURCE_PATH
    if not source_path:
        logger.warning(
            "HydroLAKES source path not configured; no lakes imported",
            country=country,
        )
        return []

    with open(source_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    features = data.get("features", []) if isinstance(data, dict) else data
    lakes: list[dict] = []
    for feature in features:
        props = feature.get("properties", {}) if isinstance(feature, dict) else {}
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        lake_country = str(props.get("country") or props.get("COUNTRY") or "").strip()
        if lake_country.lower() != country.lower():
            continue

        geom_obj = shape(geometry) if geometry else None
        centroid = geom_obj.centroid if geom_obj is not None else None
        bbox = list(geom_obj.bounds) if geom_obj is not None else None

        hydrolake_id = str(
            props.get("Hylak_id")
            or props.get("HYLAK_ID")
            or props.get("hydrolake_id")
            or props.get("id")
        )
        name = _normalize_lake_label(props.get("Lake_name") or props.get("name") or hydrolake_id)
        area_sqkm = float(
            props.get("Lake_area")
            or props.get("area_sqkm")
            or props.get("area")
            or 0.0
        )

        lakes.append(
            {
                "hydrolake_id": hydrolake_id,
                "name": name,
                "country": lake_country or country,
                "center_lat": float(centroid.y if centroid is not None else props.get("lat", 0.0)),
                "center_lon": float(centroid.x if centroid is not None else props.get("lon", 0.0)),
                "area_sqkm": area_sqkm,
                "bbox": bbox,
                "geom_wkt": geom_obj.wkt if geom_obj is not None else None,
            }
        )

    return lakes


def _register_sync_job(job_id: str) -> None:
    with _SYNC_LOCK:
        _ACTIVE_SYNC_JOBS[job_id] = {"cancel_requested": False}


def _clear_sync_job(job_id: str) -> None:
    with _SYNC_LOCK:
        _ACTIVE_SYNC_JOBS.pop(job_id, None)


def _cancel_sync_job(job_id: str) -> bool:
    with _SYNC_LOCK:
        if job_id not in _ACTIVE_SYNC_JOBS:
            return False
        _ACTIVE_SYNC_JOBS[job_id]["cancel_requested"] = True
        return True


def _is_sync_cancelled(job_id: str) -> bool:
    with _SYNC_LOCK:
        return bool(_ACTIVE_SYNC_JOBS.get(job_id, {}).get("cancel_requested", False))


def is_sync_cancelled(job_id: str | None = None) -> bool:
    with _SYNC_LOCK:
        if job_id is None:
            return any(bool(job.get("cancel_requested", False)) for job in _ACTIVE_SYNC_JOBS.values())
        return bool(_ACTIVE_SYNC_JOBS.get(job_id, {}).get("cancel_requested", False))


def cancel_sync(job_id: str | None = None) -> dict:
    """Cancel one active sync job, or all active jobs when no job ID is provided."""
    with _SYNC_LOCK:
        if job_id is None:
            for active_job_id in list(_ACTIVE_SYNC_JOBS):
                _ACTIVE_SYNC_JOBS[active_job_id]["cancel_requested"] = True
            _SYNC_PROGRESS["status"] = "cancelled"
            _SYNC_PROGRESS["current_lake"] = None
            _SYNC_PROGRESS["current_year"] = None
            return {"job_id": None, "cancelled": True, "active_jobs": len(_ACTIVE_SYNC_JOBS)}

        if job_id in _ACTIVE_SYNC_JOBS:
            _ACTIVE_SYNC_JOBS[job_id]["cancel_requested"] = True
            _SYNC_PROGRESS["status"] = "cancelled"
            _SYNC_PROGRESS["current_lake"] = None
            _SYNC_PROGRESS["current_year"] = None
            return {"job_id": job_id, "cancelled": True}
        return {"job_id": job_id, "cancelled": False}


def list_hydrolake_boundaries(country: str = "India") -> list[HydroLakeBoundaryResponse]:
    responses: list[HydroLakeBoundaryResponse] = []
    for lake in _load_lake_records(country):
        geometry = None
        if lake.get("geom_wkt"):
            geometry = shapely_wkt.loads(lake["geom_wkt"]).__geo_interface__
        responses.append(
            HydroLakeBoundaryResponse(
                hydrolake_id=lake["hydrolake_id"],
                name=lake["name"],
                country=lake["country"],
                center_lat=lake["center_lat"],
                center_lon=lake["center_lon"],
                area_sqkm=lake["area_sqkm"],
                bbox=lake["bbox"],
                geometry=geometry,
            )
        )
    return responses


def _state_name(properties: dict) -> str | None:
    """Read the state name from common India boundary-file attribute names."""
    normalized = {str(key).lower(): value for key, value in properties.items()}
    for field in INDIA_STATE_NAME_FIELDS:
        value = normalized.get(field)
        if value is not None and str(value).strip():
            return _normalize_lake_label(value)
    return None


def _load_india_state_rows(source_path: str) -> list[dict]:
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"India states boundary file not found at {source_path}")

    suffix = Path(source_path).suffix.lower()
    rows: list[dict] = []
    if suffix in {".json", ".geojson"}:
        with open(source_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        features = data.get("features", []) if isinstance(data, dict) else data
        for feature in features:
            if not isinstance(feature, dict):
                continue
            state_name = _state_name(feature.get("properties") or {})
            geometry_data = feature.get("geometry")
            if not state_name or not geometry_data:
                continue
            geometry = shape(geometry_data)
            rows.append({"state_name": state_name, "geom_wkt": geometry.wkt})
    elif suffix == ".shp":
        try:
            import shapefile  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency/runtime guard
            raise RuntimeError(f"Shapefile reader unavailable: {exc}") from exc
        reader = shapefile.Reader(source_path, encoding="cp1252", encodingErrors="replace")
        fields = [field[0] for field in reader.fields[1:]]
        for shape_record in reader.iterShapeRecords():
            properties = (
                shape_record.record.as_dict()
                if hasattr(shape_record.record, "as_dict")
                else dict(zip(fields, shape_record.record))
            )
            state_name = _state_name(properties)
            if not state_name or not shape_record.shape:
                continue
            geometry = shape(shape_record.shape.__geo_interface__)
            rows.append({"state_name": state_name, "geom_wkt": geometry.wkt})
    else:
        raise ValueError("India state boundaries must be a .shp, .json, or .geojson file")

    if not rows:
        raise ValueError("No valid India state boundaries were found in the source file")
    return rows


def _refresh_lake_state_metadata(conn) -> int:
    """Populate centroid, state, and display name from the imported boundaries."""
    from sqlalchemy import text  # noqa: PLC0415

    result = conn.execute(
        text(
            """
            WITH attributed_lakes AS (
                SELECT
                    lake_id,
                    ST_Centroid(geom) AS centroid,
                    (
                        SELECT translate(state_name, 'āĀ', 'aA') AS state_name
                        FROM india_states
                        WHERE ST_Covers(geom, ST_Centroid(lakes.geom))
                        ORDER BY state_name
                        LIMIT 1
                    ) AS state
                FROM lakes
                WHERE lower(country) = 'india'
            )
            UPDATE lakes AS lake
            SET
                centroid = attributed.centroid,
                state = attributed.state,
                display_name = CASE
                    WHEN lake.lake_name IS NOT NULL AND btrim(lake.lake_name) <> ''
                         AND btrim(lake.lake_name) <> lake.lake_id::text
                        THEN lake.lake_name
                    WHEN attributed.state IS NOT NULL
                        THEN format('Unnamed Lake #%s (%s)', lake.lake_id, attributed.state)
                    ELSE format('Unnamed Lake #%s', lake.lake_id)
                END,
                updated_at = NOW()
            FROM attributed_lakes AS attributed
            WHERE lake.lake_id = attributed.lake_id
            """
        )
    )
    return result.rowcount


def import_india_states(source_path: str | None = None) -> dict:
    """Store India state/UT boundaries and backfill state metadata for existing lakes."""
    from sqlalchemy import text  # noqa: PLC0415

    path = source_path or INDIA_STATES_SOURCE_PATH
    if not path:
        raise FileNotFoundError(
            "INDIA_STATES_SOURCE_PATH is not configured; set it to an India states GeoJSON or shapefile."
        )

    state_rows = _load_india_state_rows(path)
    upsert_statement = text(
        """
        INSERT INTO india_states (state_name, geom)
        SELECT state_name, ST_Multi(ST_GeomFromText(geom_wkt, 4326))
        FROM jsonb_to_recordset(CAST(:state_rows AS jsonb)) AS source(
            state_name text,
            geom_wkt text
        )
        ON CONFLICT (state_name) DO UPDATE SET
            geom = EXCLUDED.geom,
            updated_at = NOW()
        """
    )
    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            for start in range(0, len(state_rows), LAKE_IMPORT_BATCH_SIZE):
                conn.execute(
                    upsert_statement,
                    {"state_rows": json.dumps(state_rows[start : start + LAKE_IMPORT_BATCH_SIZE])},
                )
            lakes_updated = _refresh_lake_state_metadata(conn)
    finally:
        engine.dispose()

    return {
        "source_path": path,
        "states_stored": len(state_rows),
        "lakes_updated": lakes_updated,
    }


def _ensure_india_states_available() -> None:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    try:
        with engine.connect() as conn:
            states_exist = conn.execute(text("SELECT EXISTS (SELECT 1 FROM india_states)")).scalar()
    finally:
        engine.dispose()

    if not states_exist:
        import_india_states()


def import_lakes_table(country: str = "India") -> dict:
    try:
        import shapefile  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError(f"Shapefile reader unavailable: {exc}") from exc

    source_path = HYDROLAKES_SHAPEFILE_PATH
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"HydroLAKES shapefile not found at {source_path}")
    if country.lower() == "india":
        _ensure_india_states_available()

    # HydroLAKES DBF attributes use Windows-1252 characters (for example,
    # curly apostrophes), rather than UTF-8.
    reader = shapefile.Reader(source_path, encoding="cp1252", encodingErrors="replace")
    total_records = len(reader)
    inserted_records = 0
    updated_records = 0
    skipped_records = 0
    lake_rows: list[dict] = []

    # The HydroLAKES geometry file is more than 1 GB.  Reading every shape
    # before checking its country is what made India imports exceed the client
    # timeout.  Scan the much smaller DBF attributes first, then seek directly
    # to geometries belonging to the requested country.
    fields = [field[0] for field in reader.fields[1:]]
    for record_index, source_record in enumerate(reader.iterRecords()):
        try:
            record = (
                source_record.as_dict()
                if hasattr(source_record, "as_dict")
                else dict(zip(fields, source_record))
            )
            normalized = {str(key).lower(): value for key, value in record.items()}
            record_country = str(normalized.get("country") or normalized.get("COUNTRY") or "").strip()
            if country and record_country.lower() != country.lower():
                continue

            lake_id_value = normalized.get("hylak_id") or normalized.get("lake_id") or normalized.get("id")
            if lake_id_value in (None, ""):
                skipped_records += 1
                continue

            source_shape = reader.shape(record_index)
            geometry = shape(source_shape.__geo_interface__) if source_shape else None
            lake_rows.append(
                {
                    "lake_id": int(float(lake_id_value)),
                    "lake_name": _normalize_lake_label(
                        normalized.get("lake_name") or normalized.get("name") or ""
                    )
                    or None,
                    "country": record_country or country,
                    "area_sqkm": float(normalized.get("lake_area") or normalized.get("area_sqkm") or normalized.get("area") or 0.0),
                    "elevation": float(normalized.get("elevation") or 0.0) if normalized.get("elevation") not in (None, "") else None,
                    "pour_lat": float(normalized.get("pour_lat") or normalized.get("lat") or 0.0) if normalized.get("pour_lat") not in (None, "") or normalized.get("lat") not in (None, "") else None,
                    "pour_long": float(normalized.get("pour_long") or normalized.get("lon") or 0.0) if normalized.get("pour_long") not in (None, "") or normalized.get("lon") not in (None, "") else None,
                    "lake_type": str(normalized.get("lake_type") or normalized.get("type") or "").strip() or None,
                    "depth_avg": float(normalized.get("depth_avg") or 0.0) if normalized.get("depth_avg") not in (None, "") else None,
                    "vol_total": float(normalized.get("vol_total") or 0.0) if normalized.get("vol_total") not in (None, "") else None,
                    "wshd_area": float(normalized.get("wshd_area") or 0.0) if normalized.get("wshd_area") not in (None, "") else None,
                    "geom_wkt": geometry.wkt if geometry is not None else None,
                }
            )
        except Exception:
            skipped_records += 1

    from sqlalchemy import text  # noqa: PLC0415

    # Importing one lake at a time previously issued a SELECT and an INSERT for
    # every record.  India has enough HydroLAKES polygons for that N+1 pattern
    # to exceed the frontend's request timeout.  Send each batch to Postgres as
    # one JSON recordset and let the database perform the upsert set-wise.
    upsert_statement = text(
        """
        WITH source_rows AS (
            SELECT *
            FROM jsonb_to_recordset(CAST(:lake_rows AS jsonb)) AS source(
                lake_id bigint,
                lake_name text,
                country text,
                area_sqkm double precision,
                elevation double precision,
                pour_lat double precision,
                pour_long double precision,
                lake_type text,
                depth_avg double precision,
                vol_total double precision,
                wshd_area double precision,
                geom_wkt text
            )
        ),
        lake_geometries AS (
            SELECT
                *,
                CASE WHEN geom_wkt IS NULL THEN NULL ELSE ST_Multi(ST_GeomFromText(geom_wkt, 4326)) END AS geom
            FROM source_rows
        ),
        centroids AS MATERIALIZED (
            SELECT *, ST_Centroid(geom) AS centroid
            FROM lake_geometries
        ),
        attributed_rows AS (
            SELECT centroids.*, matched_state.state_name AS state
            FROM centroids
            LEFT JOIN LATERAL (
                SELECT translate(state_name, 'āĀ', 'aA') AS state_name
                FROM india_states
                WHERE lower(centroids.country) = 'india'
                  AND geom && centroids.centroid
                  AND ST_Covers(geom, centroids.centroid)
                ORDER BY state_name
                LIMIT 1
            ) AS matched_state ON TRUE
        ),
        upserted AS (
            INSERT INTO lakes (
                lake_id, lake_name, country, area_sqkm, elevation,
                pour_lat, pour_long, lake_type, depth_avg, vol_total,
                wshd_area, geom, centroid, state, display_name
            )
            SELECT
                lake_id, lake_name, country, area_sqkm, elevation,
                pour_lat, pour_long, lake_type, depth_avg, vol_total,
                wshd_area, geom, centroid, state,
                CASE
                    WHEN lake_name IS NOT NULL AND btrim(lake_name) <> ''
                         AND btrim(lake_name) <> lake_id::text THEN lake_name
                    WHEN state IS NOT NULL THEN format('Unnamed Lake #%s (%s)', lake_id, state)
                    ELSE format('Unnamed Lake #%s', lake_id)
                END
            FROM attributed_rows
            ON CONFLICT (lake_id) DO UPDATE SET
                lake_name = EXCLUDED.lake_name,
                country = EXCLUDED.country,
                area_sqkm = EXCLUDED.area_sqkm,
                elevation = EXCLUDED.elevation,
                pour_lat = EXCLUDED.pour_lat,
                pour_long = EXCLUDED.pour_long,
                lake_type = EXCLUDED.lake_type,
                depth_avg = EXCLUDED.depth_avg,
                vol_total = EXCLUDED.vol_total,
                wshd_area = EXCLUDED.wshd_area,
                geom = EXCLUDED.geom,
                centroid = EXCLUDED.centroid,
                state = EXCLUDED.state,
                display_name = EXCLUDED.display_name,
                updated_at = NOW()
            RETURNING xmax = 0 AS inserted
        )
        SELECT
            COUNT(*) FILTER (WHERE inserted) AS inserted_records,
            COUNT(*) FILTER (WHERE NOT inserted) AS updated_records
        FROM upserted
        """
    )

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            for start in range(0, len(lake_rows), LAKE_IMPORT_BATCH_SIZE):
                batch = lake_rows[start : start + LAKE_IMPORT_BATCH_SIZE]
                counts = conn.execute(
                    upsert_statement,
                    {"lake_rows": json.dumps(batch)},
                ).mappings().one()
                inserted_records += int(counts["inserted_records"])
                updated_records += int(counts["updated_records"])
    finally:
        engine.dispose()

    return {
        "source_path": source_path,
        "country": country,
        "total_records": total_records,
        "inserted_records": inserted_records,
        "updated_records": updated_records,
        "skipped_records": skipped_records,
        "message": f"Stored {inserted_records + updated_records} lake record(s) for {country}.",
    }


def _wipe_country_sub_regions(country: str) -> None:
    """Remove generated processing cells for a country before a refresh."""
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM sub_regions AS sub_region
                    USING lakes AS lake
                    WHERE sub_region.lake_id = lake.lake_id
                      AND lower(lake.country) = lower(:country)
                    """
                ),
                {"country": country},
            )
    finally:
        engine.dispose()


def _create_lake_sub_regions(country: str, years: list[int], states: list[str] | None = None) -> list[dict]:
    """Create valid 1 km processing cells and return one row per cell/year.

    The grid is built in EPSG:6933 (a metre-based equal-area CRS), then
    transformed back to WGS84 for storage and the GEE request.  Coverage is
    the percentage of each full grid cell occupied by the lake polygon.
    """
    from sqlalchemy import text  # noqa: PLC0415

    if not years:
        return []

    statement = text(
        """
        WITH lake_cells AS (
            SELECT
                lake.lake_id,
                grid.geom AS metric_geom,
                ST_Transform(lake.geom, 6933) AS lake_metric_geom
            FROM lakes AS lake
            CROSS JOIN LATERAL ST_SquareGrid(
                :cell_size_metres, ST_Transform(lake.geom, 6933)
            ) AS grid
            WHERE lower(lake.country) = lower(:country)
              AND lake.is_active = true
              AND lake.geom IS NOT NULL
              AND (:states IS NULL OR lake.state = ANY(CAST(:states AS text[])))
        ),
        valid_cells AS (
            SELECT
                lake_id,
                metric_geom,
                100.0 * ST_Area(ST_Intersection(metric_geom, lake_metric_geom))
                    / NULLIF(ST_Area(metric_geom), 0) AS coverage_percent
            FROM lake_cells
            WHERE ST_Intersects(metric_geom, lake_metric_geom)
        ),
        numbered_cells AS (
            SELECT
                lake_id,
                ROW_NUMBER() OVER (
                    PARTITION BY lake_id
                    ORDER BY ST_Y(ST_Centroid(metric_geom)), ST_X(ST_Centroid(metric_geom))
                )::integer AS cell_number,
                ST_Transform(metric_geom, 4326) AS geom,
                coverage_percent
            FROM valid_cells
            WHERE coverage_percent >= :minimum_coverage_percent
        ),
        inserted AS (
            INSERT INTO sub_regions (
                sub_region_id, lake_id, cell_number, year, coverage_percent,
                center_lat, center_lon, geom
            )
            SELECT
                gen_random_uuid(), numbered_cells.lake_id, numbered_cells.cell_number,
                requested_year.year, numbered_cells.coverage_percent,
                ST_Y(ST_Centroid(numbered_cells.geom)),
                ST_X(ST_Centroid(numbered_cells.geom)),
                numbered_cells.geom
            FROM numbered_cells
            CROSS JOIN unnest(CAST(:years AS integer[])) AS requested_year(year)
            ON CONFLICT (lake_id, cell_number, year) DO UPDATE SET
                coverage_percent = EXCLUDED.coverage_percent,
                center_lat = EXCLUDED.center_lat,
                center_lon = EXCLUDED.center_lon,
                geom = EXCLUDED.geom,
                updated_at = NOW()
            RETURNING sub_region_id, lake_id, cell_number, year, center_lat, center_lon,
                      coverage_percent, ST_AsText(geom) AS geom_wkt
        )
        SELECT * FROM inserted
        ORDER BY lake_id, cell_number, year
        """
    )
    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                statement,
                {
                    "country": country,
                    "years": years,
                    "states": states,
                    "cell_size_metres": settings.LAKE_GRID_CELL_SIZE_METRES,
                    "minimum_coverage_percent": settings.LAKE_GRID_MIN_COVERAGE_PERCENT,
                },
            ).mappings().all()
        return [
            {
                "sub_region_id": str(row["sub_region_id"]),
                "lake_id": int(row["lake_id"]),
                "cell_number": int(row["cell_number"]),
                "year": int(row["year"]),
                "center_lat": float(row["center_lat"]),
                "center_lon": float(row["center_lon"]),
                "coverage_percent": float(row["coverage_percent"]),
                "geom_wkt": row["geom_wkt"],
            }
            for row in rows
        ]
    finally:
        engine.dispose()


def _load_selected_regions(region_ids: list[str]) -> list[dict]:
    from sqlalchemy import text  # noqa: PLC0415

    if not region_ids:
        return []

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT region_id, hydrolake_id, name, country, center_lat, center_lon,
                           area_sqkm, bbox, ST_AsText(geom) AS geom_wkt
                    FROM regions
                    WHERE region_id = ANY(:region_ids)
                    ORDER BY name ASC
                    """
                ),
                {"region_ids": region_ids},
            ).mappings().all()

        regions: list[dict] = []
        for row in rows:
            regions.append(
                {
                    "region_id": str(row["region_id"]),
                    "hydrolake_id": row["hydrolake_id"],
                    "name": row["name"],
                    "country": row["country"],
                    "center_lat": float(row["center_lat"]),
                    "center_lon": float(row["center_lon"]),
                    "area_sqkm": float(row["area_sqkm"] or 0.0),
                    "bbox": row["bbox"],
                    "geom_wkt": row["geom_wkt"],
                }
            )
        return regions
    finally:
        engine.dispose()


def _upsert_region_row(lake: dict) -> tuple[str, bool]:
    from sqlalchemy import text  # noqa: PLC0415

    engine = _sync_engine()
    try:
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT region_id FROM regions WHERE hydrolake_id = :hydrolake_id"),
                {"hydrolake_id": lake["hydrolake_id"]},
            ).scalar_one_or_none()
            region_id = existing or str(uuid.uuid5(uuid.NAMESPACE_URL, f"hydrolakes:{lake['hydrolake_id']}"))
            conn.execute(
                text(
                    """
                    INSERT INTO regions (
                        region_id, hydrolake_id, name, country,
                        center_lat, center_lon, area_sqkm, bbox, geom
                    )
                    VALUES (
                        :region_id, :hydrolake_id, :name, :country,
                        :center_lat, :center_lon, :area_sqkm, CAST(:bbox AS jsonb),
                        CASE WHEN :geom_wkt IS NULL THEN NULL ELSE ST_GeomFromText(:geom_wkt, 4326) END
                    )
                    ON CONFLICT (hydrolake_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        country = EXCLUDED.country,
                        center_lat = EXCLUDED.center_lat,
                        center_lon = EXCLUDED.center_lon,
                        area_sqkm = EXCLUDED.area_sqkm,
                        bbox = EXCLUDED.bbox,
                        geom = EXCLUDED.geom,
                        updated_at = NOW()
                    """
                ),
                {
                    "region_id": region_id,
                    "hydrolake_id": lake["hydrolake_id"],
                    "name": lake["name"],
                    "country": lake["country"],
                    "center_lat": lake["center_lat"],
                    "center_lon": lake["center_lon"],
                    "area_sqkm": lake["area_sqkm"],
                    "bbox": json.dumps(lake["bbox"]) if lake.get("bbox") is not None else None,
                    "geom_wkt": lake.get("geom_wkt"),
                },
            )
        return region_id, existing is None
    finally:
        engine.dispose()


def start_sync(request: SyncRequest, job_id: str | None = None) -> SyncJobResponse:
    if not job_id:
        job_id = str(uuid.uuid4())
    _register_sync_job(job_id)
    years = request.duration.resolved_years()
    log = logger.bind(job_id=job_id, country=request.country, years=years)
    log.info("Sync job started", sync_mode=request.sync_mode)

    source_regions = (
        _load_selected_regions(request.region_ids or [])
        if request.source_type == SyncSource.STORED_REGIONS
        else []
    )

    backup_path: str | None = None
    if request.sync_mode == SyncMode.BACKUP:
        try:
            backup_path = _pg_dump(job_id)
        except Exception as exc:
            log.error("Backup failed — aborting sync", error=str(exc))
            return SyncJobResponse(
                job_id=job_id,
                status="failed",
                source_type=request.source_type,
                country=request.country,
                region_ids=request.region_ids or [],
                years=years,
                sync_mode=request.sync_mode,
                tasks_dispatched=0,
                total_regions=0,
                inserted_regions=0,
                updated_regions=0,
                skipped_regions=0,
                message=f"Backup failed: {exc}",
                backup_path=None,
            )

    try:
        if request.sync_mode == SyncMode.REFRESH:
            if request.source_type == SyncSource.HYDROLAKES:
                _wipe_country_sub_regions(request.country)
            else:
                _wipe_country_data(request.country)
    except Exception as exc:
        log.error("DB wipe failed", error=str(exc))
        return SyncJobResponse(
            job_id=job_id,
            status="failed",
            source_type=request.source_type,
            country=request.country,
            region_ids=request.region_ids or [],
            years=years,
            sync_mode=request.sync_mode,
            tasks_dispatched=0,
            total_regions=len(source_regions),
            inserted_regions=0,
            updated_regions=0,
            skipped_regions=0,
            message=f"DB wipe failed: {exc}",
            backup_path=backup_path,
        )

    inserted_regions = 0
    updated_regions = 0
    skipped_regions = 0
    region_jobs: list[dict] = []
    if request.source_type == SyncSource.HYDROLAKES:
        try:
            region_jobs = _create_lake_sub_regions(request.country, years, states=request.states)
            inserted_regions = len(region_jobs)
        except Exception as exc:
            log.error("Could not create lake sub-regions", error=str(exc))
            return SyncJobResponse(
                job_id=job_id,
                status="failed",
                source_type=request.source_type,
                country=request.country,
                region_ids=[],
                years=years,
                sync_mode=request.sync_mode,
                tasks_dispatched=0,
                total_regions=0,
                inserted_regions=0,
                updated_regions=0,
                skipped_regions=0,
                message=f"Could not create lake sub-regions: {exc}",
                backup_path=backup_path,
            )
    else:
        region_jobs = source_regions

    for lake in region_jobs:
        try:
            if request.source_type == SyncSource.STORED_REGIONS and not lake.get("region_id"):
                raise ValueError("Stored region selection missing region_id")
        except Exception as exc:
            skipped_regions += 1
            log.warning("Could not prepare selected region", error=str(exc))

    from app.embedding_pipeline.pipeline import run_embedding_pipeline  # noqa: PLC0415

    # ── Collect unique lake IDs and years from the generated sub-regions ───
    lake_ids_set: set[int] = set()
    unique_years: set[int] = set()
    for lake in region_jobs:
        lake_id_val = lake.get("lake_id")
        if lake_id_val is not None:
            lake_ids_set.add(int(lake_id_val))
        year_val = lake.get("year")
        if year_val is not None:
            unique_years.add(int(year_val))

    # Fall back to the request years when region_jobs don't carry a year
    if not unique_years:
        unique_years = set(years)

    sorted_lake_ids = sorted(lake_ids_set)
    sorted_years = sorted(unique_years)
    total_lake_year_pairs = len(sorted_lake_ids) * len(sorted_years)

    # ── Initialise global progress ────────────────────────────────────────────
    with _SYNC_LOCK:
        _SYNC_PROGRESS.update({
            "status": "running",
            "total_lakes": total_lake_year_pairs,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "current_lake": None,
            "current_year": None,
            "errors": [],
        })

    # ── Run the local embedding pipeline ──────────────────────────────────────
    # The embedding pipeline handles: GeoTIFF lookup from lake_images,
    # grid generation, cell extraction, GPU-batched Prithvi inference,
    # and per-cell storage (sub_regions / sub_region_features). It respects
    # sync cancellation
    # via check_sync_cancel=True.
    tasks_dispatched = 0
    try:
        emb_result = run_embedding_pipeline(
            lake_ids=sorted_lake_ids if sorted_lake_ids else None,
            years=sorted_years if sorted_years else None,
            check_sync_cancel=True,
        )
        tasks_dispatched = emb_result.get("success", 0) + emb_result.get("failed", 0)

        # Bridge embedding pipeline results to sync progress
        with _SYNC_LOCK:
            _SYNC_PROGRESS["success"] = emb_result.get("success", 0)
            _SYNC_PROGRESS["failed"] = emb_result.get("failed", 0)
            _SYNC_PROGRESS["processed"] = (
                emb_result.get("success", 0)
                + emb_result.get("failed", 0)
                + emb_result.get("skipped", 0)
            )
            if emb_result.get("cancelled"):
                _SYNC_PROGRESS["status"] = "cancelled"

    except Exception as exc:
        err_msg = f"Embedding pipeline error: {exc}"
        log.error("Embedding pipeline failed", error=str(exc))
        with _SYNC_LOCK:
            _SYNC_PROGRESS["errors"].append(err_msg)
            _SYNC_PROGRESS["failed"] += 1
            _SYNC_PROGRESS["processed"] += 1

    # ── Mark done or cancelled ─────────────────────────────────────────────
    with _SYNC_LOCK:
        if _is_sync_cancelled(job_id):
            _SYNC_PROGRESS["status"] = "cancelled"
        elif _SYNC_PROGRESS["status"] != "cancelled":
            _SYNC_PROGRESS["status"] = "done"
        _SYNC_PROGRESS["current_lake"] = None
        _SYNC_PROGRESS["current_year"] = None

    log.info(
        "Lake regions imported",
        total_regions=len(region_jobs),
        inserted_regions=inserted_regions,
        updated_regions=updated_regions,
        skipped_regions=skipped_regions,
        tasks_dispatched=tasks_dispatched,
    )

    status = "cancelled" if _is_sync_cancelled(job_id) else "completed"
    _clear_sync_job(job_id)

    return SyncJobResponse(
        job_id=job_id,
        status=status,
        source_type=request.source_type,
        country=request.country,
        region_ids=[lake.get("sub_region_id") or lake.get("lake_id", "") for lake in region_jobs],
        years=years,
        sync_mode=request.sync_mode,
        tasks_dispatched=tasks_dispatched,
        total_regions=len(region_jobs),
        inserted_regions=inserted_regions,
        updated_regions=updated_regions,
        skipped_regions=skipped_regions,
        backup_path=backup_path,
        message=(
            f"Created {len(region_jobs)} valid sub-region(s) and generated embeddings for {request.country}."
            if request.source_type == SyncSource.HYDROLAKES
            else f"Generated embeddings for {len(region_jobs)} stored region(s)."
        ),
    )


def get_sync_progress() -> dict:
    """Return a snapshot of the current (or last completed) sync progress."""
    with _SYNC_LOCK:
        return dict(_SYNC_PROGRESS)
