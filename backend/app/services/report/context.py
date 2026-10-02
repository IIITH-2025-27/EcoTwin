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
from app.schemas.forecast import EcologicalForecastResponse
from app.schemas.similarity import SimilarityMethod
from app.services.ecological_forecast_service import EcologicalForecastService
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


# Same five series, colours, and ordering as ECO_CHART_INDICES in
# frontend/src/components/ForecastPanel/ForecastPanel.tsx, so the report
# chart matches what the Forecast panel renders in the UI.
_ECO_CHART_INDICES: list[tuple[str, str, str]] = [
    ("ndci", "NDCI", "#06b6d4"),
    ("ndvi", "NDVI", "#22c55e"),
    ("ndwi", "NDWI", "#3b82f6"),
    ("turbidity_ratio", "Turbidity", "#f59e0b"),
    ("red_edge_slope", "RE Slope", "#a855f7"),
]


def _build_twin_delta_rows(yearly_directions: list) -> list["TwinDeltaRow"]:
    """Pivot per-year twin deltas into one row per twin lake, keyed by year.

    Mirrors the ``TwinDeltaChart`` pivot in ForecastPanel.tsx: each twin
    (identified by its rank) becomes a row, and its raw delta at each
    forecast year (matched_year -> matched_year + offset, from the twin's
    own observed data) becomes one bar in that row.
    """
    by_rank: dict[int, TwinDeltaRow] = {}
    for yd in yearly_directions:
        for td in yd.twin_deltas:
            row = by_rank.get(td.rank)
            if row is None:
                row = TwinDeltaRow(
                    lake_id=td.lake_id,
                    rank=td.rank,
                    fixed_weight=td.fixed_weight,
                    matched_year=td.matched_year,
                )
                by_rank[td.rank] = row
            row.bars[yd.year] = TwinDeltaBar(
                year=yd.year,
                delta=td.delta,
                normalized_weight=td.normalized_weight,
                weighted_contribution=td.weighted_contribution,
            )
    return sorted(by_rank.values(), key=lambda r: r.rank)


def _build_eco_forecast_items(
    eco: EcologicalForecastResponse,
) -> list[EcoIndexForecastItem]:
    """Compute each index's chart series + expected value change.

    Uses the ``expected_value`` and ``twin_deltas`` the backend already
    computed in ``EcologicalForecastService`` (current_value + that year's
    twin-weighted score) — the same fields the Forecast panel chart and its
    twin-delta chart consume, so the report matches the UI exactly.
    """
    years = [eco.current_year, *eco.forecast_years]
    forecast_by_index = {f.index_name: f for f in eco.index_forecasts}

    items: list[EcoIndexForecastItem] = []
    for key, label, color in _ECO_CHART_INDICES:
        forecast_entry = forecast_by_index.get(key)
        base_value = forecast_entry.current_value if forecast_entry else 0.0
        yearly_directions = forecast_entry.yearly_directions if forecast_entry else []

        points: list[tuple[int, float]] = [(years[0], base_value)]
        for offset, year in enumerate(years[1:], start=0):
            if offset < len(yearly_directions):
                yd = yearly_directions[offset]
                value = yd.expected_value if yd.expected_value is not None else base_value
            else:
                value = base_value
            points.append((year, value))

        yearly_changes: list[EcoIndexYearChange] = []
        for offset, (year, value) in enumerate(points[1:]):
            change = value - base_value
            change_pct = (change / abs(base_value) * 100) if base_value else None
            direction = (
                yearly_directions[offset].direction
                if offset < len(yearly_directions)
                else "uncertain"
            )
            yearly_changes.append(
                EcoIndexYearChange(
                    year=year,
                    value=value,
                    change=change,
                    change_pct=change_pct,
                    direction=direction,
                )
            )

        final_change = yearly_changes[-1].change if yearly_changes else 0.0
        final_change_pct = yearly_changes[-1].change_pct if yearly_changes else None
        final_direction = yearly_changes[-1].direction if yearly_changes else "uncertain"

        items.append(
            EcoIndexForecastItem(
                key=key,
                label=label,
                color=color,
                current_value=base_value,
                points=points,
                yearly_changes=yearly_changes,
                final_change=final_change,
                final_change_pct=final_change_pct,
                final_direction=final_direction,
                twin_delta_rows=_build_twin_delta_rows(yearly_directions),
            )
        )

    return items


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
    # Current-value snapshot of the same 5 ecological indices shown in the
    # Forecast section (Section 5) — same EcoIndexForecastItem objects,
    # reused here rather than requeried, just for their .label/.color/
    # .current_value; Overview shows the snapshot, Forecast shows the trend.
    ecological_indices: list = field(default_factory=list)


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
class EcoIndexYearChange:
    """One forecast year's projected value and change vs. the current value."""

    year: int
    value: float
    change: float
    change_pct: Optional[float]
    direction: str  # "up" | "down" | "stable" | "uncertain"


@dataclass
class TwinDeltaBar:
    """One twin lake's raw delta bar for one forecast year."""

    year: int
    delta: float
    normalized_weight: float  # this twin's renormalized weight for this specific year
    weighted_contribution: float


@dataclass
class TwinDeltaRow:
    """One twin lake's delta bars across all forecast years, for one index."""

    lake_id: int
    rank: int
    fixed_weight: float  # rank-based weight, constant across years — see normalized_weight per bar
    matched_year: int
    bars: dict[int, TwinDeltaBar] = field(default_factory=dict)


@dataclass
class EcoIndexForecastItem:
    """One ecological index's chart series + expected value change (Section 5).

    Mirrors the series the Forecast panel chart renders in the UI so the
    report shows the same trajectory the user already sees there.
    """

    key: str
    label: str
    color: str
    current_value: float
    points: list[tuple[int, float]] = field(default_factory=list)
    yearly_changes: list[EcoIndexYearChange] = field(default_factory=list)
    final_change: float = 0.0
    final_change_pct: Optional[float] = None
    final_direction: str = "uncertain"
    twin_delta_rows: list[TwinDeltaRow] = field(default_factory=list)


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
    eco_forecast: list[EcoIndexForecastItem] = field(default_factory=list)
    eco_forecast_years: list[int] = field(default_factory=list)
    eco_forecast_current_year: Optional[int] = None
    eco_forecast_twin_count: int = 0


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

    eco_forecast: list[EcoIndexForecastItem] = []
    eco_forecast_years: list[int] = []
    eco_forecast_current_year: Optional[int] = None
    eco_forecast_twin_count = 0

    # ── Imagery + ecological forecast (run concurrently) ─────────────────
    # The ecological forecast and map renders are independent — run them all
    # in parallel.  Pass the already-found analog_rows to the forecast so it
    # does NOT re-run the full similarity scan (saves ~15-25s).
    bbox = _lake_bbox(geometry, center_lat, center_lon)

    async def _run_eco_forecast():
        try:
            svc = EcologicalForecastService(
                session=db,
                region_repo=RegionRepository(db),
                embedding_repo=EmbeddingRepository(db),
            )
            return await svc.generate_ecological_forecast(
                region_id=region.region_id,
                num_analogs=5,
                method=method,
                precomputed_analogs=analog_rows if analog_rows else None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Ecological forecast unavailable during report generation",
                lake_id=lake_id,
                error=str(exc),
            )
            return None

    eco_result, cover_image, boundary_image, map_image = await asyncio.gather(
        _run_eco_forecast(),
        maps.render_cover_satellite(bbox),
        maps.render_boundary_map(bbox, geometry),
        maps.render_similar_lakes_map(
            bbox=bbox,
            center=(center_lat, center_lon),
            geometry=geometry,
            analogs=analogs,
        ),
    )

    if eco_result is not None:
        eco_forecast = _build_eco_forecast_items(eco_result)
        eco_forecast_years = eco_result.forecast_years
        eco_forecast_current_year = eco_result.current_year
        eco_forecast_twin_count = len(eco_result.twins_used)


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
        ecological_indices=eco_forecast,
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
        eco_forecast=eco_forecast,
        eco_forecast_years=eco_forecast_years,
        eco_forecast_current_year=eco_forecast_current_year,
        eco_forecast_twin_count=eco_forecast_twin_count,
    )
