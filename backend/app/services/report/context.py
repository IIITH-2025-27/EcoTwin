"""Report data assembly for the EcoTwin Ecosystem Discovery Report.

This module collects every piece of data shown in the PDF report:
lake metadata, the analog (similarity) search results, the technical
details, and the generated map imagery.

Sections are intentionally kept as plain dataclasses so that new sections
(such as the completed Forecast module) can be added later by extending
``ReportContext`` without touching the renderer or the template layout.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import structlog
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LakeNotFoundException, RegionNotFoundException
from app.models.lake import Lake
from app.models.region import Region
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.similarity import SimilarityMethod
from app.services.report import maps
from app.services.similarity_service import SimilarityService

logger = structlog.get_logger(__name__)

# ── Platform constants (Section 6 — Technical Details) ──────────────────────
EMBEDDING_MODEL = "Prithvi"
EMBEDDING_DIM = 768
DATABASE_STACK = ["PostgreSQL", "PostGIS", "pgvector"]
PLATFORM_NAME = "EcoTwin Ecosystem Discovery Platform"

_EARTH_RADIUS_KM = 6_371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def format_lat_lon(lat: float, lon: float) -> str:
    """Format coordinates as ``12.3456° N, 78.9012° E``."""
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}° {lat_dir}, {abs(lon):.4f}° {lon_dir}"


def method_label(method: SimilarityMethod) -> str:
    """Human-friendly label for a similarity method."""
    labels = {
        SimilarityMethod.COSINE: "Cosine",
        SimilarityMethod.EUCLIDEAN: "Euclidean",
        SimilarityMethod.KNN: "KNN",
    }
    if isinstance(method, SimilarityMethod):
        return labels[method]
    return {v.value: label for v, label in labels.items()}.get(str(method), str(method))


def format_score(score: Optional[float]) -> str:
    """Format a similarity score as a one-decimal percentage (e.g. ``99.8%``)."""
    return f"{score * 100:.1f}%" if score is not None else "—"


# ── Section dataclasses ──────────────────────────────────────────────────────


@dataclass
class AnalogInfo:
    """One similar ecosystem (Sections 3 + 4)."""

    rank: int
    region_id: str
    lake_id: Optional[int]
    name: str
    state: Optional[str]
    country: Optional[str] = None
    similarity_score: float = 0.0
    area_sqkm: Optional[float] = None
    center_lat: float = 0.0
    center_lon: float = 0.0
    start_year: int = 0
    end_year: int = 0
    latest_year: Optional[int] = None
    distance_km: Optional[float] = None
    geometry: Optional[dict] = None
    boundary_image: Optional[str] = None


@dataclass
class SimilarityInfo:
    """Ecosystem similarity analysis summary (Section 2)."""

    method: str
    top_k: int
    response_time_ms: float
    found_count: int
    query_year: Optional[int]
    best_match: Optional[str]
    best_score: Optional[float]
    total_lakes: int = 0
    comparisons: int = 0


@dataclass
class LakeInfo:
    """Selected lake overview (Section 1)."""

    lake_id: int
    name: str
    state: Optional[str]
    country: str
    region_id: str
    center_lat: float
    center_lon: float
    area_sqkm: Optional[float]
    latest_year: Optional[int]
    geometry: Optional[dict]
    cover_image: Optional[str] = None
    boundary_image: Optional[str] = None
    map_image: Optional[str] = None


@dataclass
class TechnicalInfo:
    """Section 6 — Technical Details."""

    embedding_model: str = EMBEDDING_MODEL
    embedding_dim: int = EMBEDDING_DIM
    similarity_metric: str = ""
    database_stack: list = field(default_factory=lambda: list(DATABASE_STACK))
    library_size: int = 0
    search_detail: str = ""
    platform: str = PLATFORM_NAME
    generated_on: str = ""


@dataclass
class ReportContext:
    """Everything the report template needs, grouped by section."""

    lake: LakeInfo
    similarity: SimilarityInfo
    analogs: list = field(default_factory=list)
    technical: Optional[TechnicalInfo] = None
    summary: str = ""
    generated_at: str = ""
    has_analogs: bool = False


# ── Geometry helpers ─────────────────────────────────────────────────────────


def _geometry_bounds(geometry: Optional[dict]) -> Optional[tuple]:
    """Return ``(min_lon, min_lat, max_lon, max_lat)`` for a GeoJSON geometry."""
    if not geometry:
        return None
    coords = geometry.get("coordinates")
    if not coords:
        return None

    rings = []
    if geometry.get("type") == "Polygon":
        rings = coords
    elif geometry.get("type") == "MultiPolygon":
        for polygon in coords:
            rings.extend(polygon)
    if not rings:
        return None

    lons, lats = [], []
    for ring in rings:
        for point in ring:
            if len(point) >= 2:
                lons.append(point[0])
                lats.append(point[1])
    if not lons:
        return None
    return (min(lons), min(lats), max(lons), max(lats))


def _lake_bbox(
    geometry: Optional[dict],
    center_lat: float,
    center_lon: float,
    min_span_deg: float = 0.25,
) -> tuple:
    """Bounding box covering the lake, with a fallback around its centre."""
    bounds = _geometry_bounds(geometry)
    if bounds:
        west, south, east, north = bounds
    else:
        west, south, east, north = (
            center_lon - min_span_deg / 2,
            center_lat - min_span_deg / 2,
            center_lon + min_span_deg / 2,
            center_lat + min_span_deg / 2,
        )
    lon_span = east - west
    lat_span = north - south
    pad_lon = max(lon_span * 0.12, min_span_deg * 0.1)
    pad_lat = max(lat_span * 0.12, min_span_deg * 0.1)
    return (west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat)


# ── Context builder ──────────────────────────────────────────────────────────


def _build_summary(lake_name: str, similarity: SimilarityInfo, analogs: list) -> str:
    """One-paragraph narrative summary (Section 7)."""
    if not analogs:
        return (
            f"EcoTwin did not find any ecosystem analogs for {lake_name} within the "
            "current embedding catalogue. The lake remains available for overview, "
            "and the similarity analysis can be retried once additional historical "
            "embeddings are ingested."
        )
    count = len(analogs)
    best = analogs[0]
    plural = "" if count == 1 else "s"
    return (
        f"EcoTwin identified {count} highly similar ecosystem{plural} for {lake_name} "
        f"using geospatial foundation model embeddings. The highest similarity score "
        f"achieved was {format_score(best.similarity_score)}, indicating strong structural "
        "similarity within the learned embedding space. These ecosystem analogs provide "
        "a valuable basis for comparative ecological analysis and future forecasting "
        "capabilities."
    )


async def build_report_context(
    db: AsyncSession,
    lake_id: int,
    method: SimilarityMethod = SimilarityMethod.COSINE,
    top_k: int = 5,
) -> ReportContext:
    """Query everything needed for the report and build the section context."""
    lake = await db.scalar(
        select(Lake).where(Lake.lake_id == lake_id, Lake.is_active.is_(True))
    )
    if lake is None:
        raise LakeNotFoundException(str(lake_id))

    region = await db.scalar(
        select(Region)
        .where(Region.lake_id == lake_id, Region.embedding.is_not(None))
        .order_by(Region.year.desc())
        .limit(1)
    )
    if region is None:
        raise RegionNotFoundException(str(lake_id))

    years = (
        await db.scalars(
            select(Region.year).where(Region.lake_id == lake_id)
        )
    ).all()
    latest_year = max(years) if years else region.year

    geometry = (
        to_shape(lake.geom).__geo_interface__ if lake.geom is not None else None
    )
    centroid = to_shape(lake.centroid) if lake.centroid is not None else None
    center_lat = centroid.y if centroid is not None else region.center_lat
    center_lon = centroid.x if centroid is not None else region.center_lon

    # ── Ecosystem similarity analysis (reuses the Analog-tab search path) ────
    library_size = (
        await db.scalar(
            select(func.count(func.distinct(Region.lake_id))).where(
                Region.embedding.is_not(None)
            )
        )
        or 0
    )
    comparisons = (
        await db.scalar(
            select(func.count(Region.region_id)).where(
                Region.embedding.is_not(None)
            )
        )
        or 0
    )
    similarity_service = SimilarityService(
        embedding_repo=EmbeddingRepository(db),
        region_repo=RegionRepository(db),
    )
    similarity = SimilarityInfo(
        method=method_label(method),
        top_k=top_k,
        response_time_ms=0.0,
        found_count=0,
        query_year=latest_year,
        best_match=None,
        best_score=None,
        total_lakes=library_size,
        comparisons=comparisons,
    )
    analog_rows = []
    try:
        result = await similarity_service.search_analogs(
            region.region_id,
            top_k=top_k,
            method=method,
        )
        similarity.response_time_ms = round(result.search_latency_ms, 1)
        similarity.found_count = len(result.analogs)
        similarity.query_year = result.query_year
        analog_rows = result.analogs
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Similarity search unavailable during report generation",
            lake_id=lake_id,
            error=str(exc),
        )

    # Enrich analogs with lake display metadata (name / state / country / geometry).
    analogs: list[AnalogInfo] = []
    if analog_rows:
        region_ids = [row.region_id for row in analog_rows]
        lake_lookup_rows = (
            await db.execute(
                select(
                    Region.region_id,
                    Lake.lake_id,
                    Lake.display_name,
                    Lake.state,
                    Lake.country,
                    Lake.area_sqkm,
                    Lake.geom,
                )
                .join(Lake, Lake.lake_id == Region.lake_id)
                .where(Region.region_id.in_(region_ids))
            )
        ).all()
        lake_lookup = {row.region_id: row for row in lake_lookup_rows}

        for index, row in enumerate(analog_rows, start=1):
            meta = lake_lookup.get(row.region_id)
            analog_geometry = (
                to_shape(meta.geom).__geo_interface__ if meta is not None and meta.geom is not None else None
            )
            analogs.append(
                AnalogInfo(
                    rank=index,
                    region_id=str(row.region_id),
                    lake_id=meta.lake_id if meta else None,
                    name=(
                        meta.display_name
                        if meta
                        else (row.dominant_ecosystem or f"Lake #{row.region_id}")
                    ),
                    state=meta.state if meta else None,
                    country=meta.country if meta else None,
                    similarity_score=row.similarity_score,
                    area_sqkm=(
                        row.area_sqkm
                        if row.area_sqkm is not None
                        else (meta.area_sqkm if meta else None)
                    ),
                    center_lat=row.center_lat,
                    center_lon=row.center_lon,
                    start_year=row.start_year,
                    end_year=row.end_year,
                    latest_year=row.end_year,
                    distance_km=haversine_km(
                        center_lat, center_lon, row.center_lat, row.center_lon
                    ),
                    geometry=analog_geometry,
                )
            )

    if analogs:
        similarity.best_match = analogs[0].name
        similarity.best_score = analogs[0].similarity_score

    # ── Imagery (satellite + maps) ───────────────────────────────────────────
    bbox = _lake_bbox(geometry, center_lat, center_lon)
    cover_image = await maps.render_cover_satellite(bbox)
    boundary_image = await maps.render_boundary_map(bbox, geometry)
    map_image = await maps.render_similar_lakes_map(
        bbox=bbox,
        center=(center_lat, center_lon),
        geometry=geometry,
        analogs=analogs,
    )

    # Per-analog boundary/satellite imagery (Section 4 profiles), fetched
    # concurrently and coloured green to match the focused-analog polygon.
    if analogs:

        async def _render_analog_map(analog: AnalogInfo) -> str:
            analog_bbox = _lake_bbox(
                analog.geometry,
                analog.center_lat,
                analog.center_lon,
                min_span_deg=0.15,
            )
            image_uri = await maps.render_boundary_map(
                analog_bbox,
                analog.geometry,
                size=maps.ANALOG_MAP_SIZE,
                fill=maps.ANALOG_LAKE_FILL,
                fill_alpha=41,
                outline=maps.ANALOG_LAKE_FILL,
            )
            return image_uri or ""

        analog_images = await asyncio.gather(*(_render_analog_map(a) for a in analogs))
        for analog, image_uri in zip(analogs, analog_images):
            analog.boundary_image = image_uri or None

    lake_info = LakeInfo(
        lake_id=lake.lake_id,
        name=lake.display_name,
        state=lake.state,
        country=lake.country,
        region_id=str(region.region_id),
        center_lat=center_lat,
        center_lon=center_lon,
        area_sqkm=lake.area_sqkm,
        latest_year=latest_year,
        geometry=geometry,
        cover_image=cover_image,
        boundary_image=boundary_image,
        map_image=map_image,
    )

    now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
    generated_at = now.strftime("%B %d, %Y at %I:%M %p IST")
    technical = TechnicalInfo(
        similarity_metric=similarity.method,
        library_size=library_size,
        search_detail=(
            f"{similarity.method} similarity over "
            f"{EMBEDDING_DIM}-dimensional embeddings"
        ),
        generated_on=generated_at,
    )

    return ReportContext(
        lake=lake_info,
        similarity=similarity,
        analogs=analogs,
        technical=technical,
        summary=_build_summary(lake_info.name, similarity, analogs),
        generated_at=generated_at,
        has_analogs=bool(analogs),
    )
