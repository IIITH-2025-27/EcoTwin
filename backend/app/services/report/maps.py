"""Map & satellite imagery generation for the EcoTwin report.

The report is rendered as static HTML, so every "live" map must be baked
into a raster image before the PDF is produced. This module:

* fetches a satellite basemap from the public Esri World Imagery export
  service (no API key required), and
* overlays the lake boundary and similar-lake markers using Pillow,
  projecting lat/lon → pixel coordinates over the exported bounding box.

Every public function returns a PNG data URI (or ``None`` when the network
basemap is unavailable — the caller can then fall back to a placeholder).
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from app.services.report.context import AnalogInfo

# ── Esri World Imagery export endpoint ───────────────────────────────────────
ESRI_EXPORT_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
)
ESRI_TIMEOUT_SECONDS = 25
USER_AGENT = "Mozilla/5.0 (EcoTwin Ecosystem Discovery Platform)"

# ── Brand palette ────────────────────────────────────────────────────────────
ACCENT_SOFT = (187, 247, 208)   # primary-200 (placeholder text)
# Selected-lake polygon: matches the UI's yellow ``SelectedLakePolygon`` (#fde047).
QUERY_FILL = (253, 224, 71)
QUERY_OUTLINE = (253, 224, 71)
# Focused-analog polygon: matches the UI's green ``FocusedAnalogPolygon`` (#22c55e).
ANALOG_LAKE_FILL = (34, 197, 94)
MARKER_OUTLINE = (255, 255, 255)
CANVAS_BG = (15, 23, 42)        # slate-900 (placeholder background)
GRID_LINE = (30, 41, 59)        # slate-800

# Per-analog profile imagery size (small enough to keep the PDF lean).
ANALOG_MAP_SIZE: Tuple[int, int] = (600, 420)

_FONT_PATHS = {
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS["bold" if bold else "regular"]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def similarity_color(score: float) -> Tuple[int, int, int]:
    """Match the frontend similarity colour scale."""
    if score >= 0.85:
        return (34, 197, 94)
    if score >= 0.70:
        return (132, 204, 22)
    if score >= 0.55:
        return (234, 179, 8)
    if score >= 0.40:
        return (249, 115, 22)
    return (239, 68, 68)


def _to_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ── Basemap fetching ─────────────────────────────────────────────────────────


def _fetch_esri(bbox: Tuple[float, float, float, float], size: Tuple[int, int]) -> Image.Image:
    """Download a satellite basemap for ``bbox`` (west, south, east, north)."""
    west, south, east, north = bbox
    params = {
        "bbox": f"{west},{south},{east},{north}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{size[0]},{size[1]}",
        "format": "png32",
        "f": "image",
    }
    url = f"{ESRI_EXPORT_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=ESRI_TIMEOUT_SECONDS) as response:
        payload = response.read()
    return Image.open(io.BytesIO(payload)).convert("RGBA")


async def _fetch_esri_async(
    bbox: Tuple[float, float, float, float], size: Tuple[int, int]
) -> Image.Image:
    """Threaded basemap fetch so multiple maps can be rendered concurrently."""
    return await asyncio.to_thread(_fetch_esri, bbox, size)


def _placeholder(size: Tuple[int, int], title: str = "Satellite imagery unavailable") -> Image.Image:
    """A clean branded placeholder when the basemap cannot be fetched."""
    width, height = size
    image = Image.new("RGBA", size, CANVAS_BG + (255,))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 48):
        draw.line([(x, 0), (x, height)], fill=GRID_LINE + (255,), width=1)
    for y in range(0, height, 48):
        draw.line([(0, y), (width, y)], fill=GRID_LINE + (255,), width=1)

    font_title = _get_font(26, bold=True)
    font_sub = _get_font(16)
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(
        ((width - title_w) / 2, height / 2 - 30),
        title,
        font=font_title,
        fill=ACCENT_SOFT + (255,),
    )
    subtitle = "EcoTwin Ecosystem Discovery Platform"
    sub_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(
        ((width - sub_w) / 2, height / 2 + 6),
        subtitle,
        font=font_sub,
        fill=(100, 116, 139, 255),
    )
    return image


def _project(
    bbox: Tuple[float, float, float, float],
    size: Tuple[int, int],
):
    """Return a ``project(lon, lat) -> (x, y)`` function for the bbox/image."""
    west, south, east, north = bbox
    width, height = size

    def project(lon: float, lat: float) -> Tuple[float, float]:
        x = (lon - west) / (east - west) * width
        y = (north - lat) / (north - south) * height
        return (x, y)

    return project


# ── Drawing helpers ──────────────────────────────────────────────────────────


def _rings_from_geometry(geometry: Optional[dict]) -> List[List[List[float]]]:
    """Flatten a GeoJSON Polygon / MultiPolygon into a list of rings."""
    if not geometry:
        return []
    geo_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return []
    if geo_type == "Polygon":
        return coords
    if geo_type == "MultiPolygon":
        rings: List[List[List[float]]] = []
        for polygon in coords:
            rings.extend(polygon)
        return rings
    return []


def _draw_lake_boundary(
    draw: ImageDraw.ImageDraw,
    project,
    geometry: Optional[dict],
    *,
    fill: Tuple[int, int, int] = QUERY_FILL,
    fill_alpha: int = 46,
    outline: Tuple[int, int, int] = QUERY_OUTLINE,
) -> None:
    """Draw a lake polygon outline + translucent fill over the basemap."""
    for ring in _rings_from_geometry(geometry):
        if len(ring) < 3:
            continue
        points = [project(lon, lat) for lon, lat in ring]
        # Translucent fill (yellow for the selected lake, green for analogs —
        # matching the colours used by the interactive map).
        draw.polygon(points, fill=fill + (fill_alpha,))
        # White casing then coloured outline for visibility over satellite tiles.
        draw.line(points + [points[0]], fill=(255, 255, 255, 255), width=5, joint="curve")
        draw.line(points + [points[0]], fill=outline + (255,), width=3, joint="curve")


def _draw_marker(
    draw: ImageDraw.ImageDraw,
    project,
    lon: float,
    lat: float,
    radius: int = 14,
    fill: Tuple[int, int, int] = QUERY_FILL,
    label: Optional[str] = None,
    label_fill: Tuple[int, int, int] = (15, 23, 42),
) -> None:
    x, y = project(lon, lat)
    shadow = 4
    draw.ellipse(
        [x - radius + shadow, y - radius + shadow, x + radius + shadow, y + radius + shadow],
        fill=(0, 0, 0, 110),
    )
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        fill=MARKER_OUTLINE + (255,),
    )
    draw.ellipse(
        [x - radius + 2, y - radius + 2, x + radius - 2, y + radius - 2],
        fill=fill + (255,),
    )
    if label is not None:
        font = _get_font(15, bold=True)
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            (x - text_w / 2, y - text_h / 2 - bbox[1]),
            label,
            font=font,
            fill=label_fill + (255,),
        )


def _match_aspect(
    bbox: Tuple[float, float, float, float], size: Tuple[int, int]
) -> Tuple[float, float, float, float]:
    """Expand ``bbox`` so its aspect ratio matches the pixel ``size``.

    The Esri export adjusts the map extent to the pixel aspect ratio when
    they differ, which would silently shift the returned imagery away from
    the requested bbox. Normalising the bbox first guarantees the image maps
    linearly onto the exact bbox used for projecting the overlays.
    """
    west, south, east, north = bbox
    lon_span = east - west
    lat_span = north - south
    target = size[0] / size[1]
    current = lon_span / lat_span
    center_lon = (west + east) / 2
    center_lat = (south + north) / 2

    if current > target:
        new_lat_span = lon_span / target
        south = center_lat - new_lat_span / 2
        north = center_lat + new_lat_span / 2
    elif current < target:
        new_lon_span = lat_span * target
        west = center_lon - new_lon_span / 2
        east = center_lon + new_lon_span / 2
    return (west, south, east, north)


async def _try_base(
    bbox: Tuple[float, float, float, float], size: Tuple[int, int], label: str
) -> Image.Image:
    """Fetch the satellite basemap, falling back to a branded placeholder."""
    try:
        return await _fetch_esri_async(bbox, size)
    except Exception as exc:  # noqa: BLE001
        print(f"[report.maps] Basemap fetch failed ({label}): {exc}")
        return _placeholder(size)


# ── Public renderers (each returns a data URI or None) ───────────────────────


async def render_cover_satellite(
    bbox: Tuple[float, float, float, float],
    size: Tuple[int, int] = (1500, 1000),
) -> Optional[str]:
    """Large satellite image used on the report cover page."""
    extent = _match_aspect(bbox, size)
    image = await _try_base(extent, size, "cover")
    return _to_data_uri(image)


async def render_boundary_map(
    bbox: Tuple[float, float, float, float],
    geometry: Optional[dict],
    size: Tuple[int, int] = (900, 640),
    *,
    fill: Tuple[int, int, int] = QUERY_FILL,
    fill_alpha: int = 46,
    outline: Tuple[int, int, int] = QUERY_OUTLINE,
) -> Optional[str]:
    """Satellite basemap with a lake boundary overlaid.

    Used for the selected lake (Section 1) and for each analog lake profile
    (Section 4), coloured to match the interactive map.
    """
    extent = _match_aspect(bbox, size)
    image = await _try_base(extent, size, "boundary")
    draw = ImageDraw.Draw(image)
    _draw_lake_boundary(
        draw,
        _project(extent, size),
        geometry,
        fill=fill,
        fill_alpha=fill_alpha,
        outline=outline,
    )
    return _to_data_uri(image)


def _analog_map_bbox(
    bbox: Tuple[float, float, float, float],
    center: Tuple[float, float],
    analogs: Sequence[AnalogInfo],
) -> Tuple[float, float, float, float]:
    """Bounding box spanning the selected lake + all similar lakes."""
    center_lat, center_lon = center
    lats = [center_lat] + [a.center_lat for a in analogs]
    lons = [center_lon] + [a.center_lon for a in analogs]

    # Always include the full selected-lake geometry so the target is visible.
    lake_w, lake_s, lake_e, lake_n = bbox
    lats.extend([lake_s, lake_n])
    lons.extend([lake_w, lake_e])

    west, south = min(lons), min(lats)
    east, north = max(lons), max(lats)
    pad_lon = max((east - west) * 0.08, 0.05)
    pad_lat = max((north - south) * 0.08, 0.05)
    return (west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat)


async def render_similar_lakes_map(
    bbox: Tuple[float, float, float, float],
    center: Tuple[float, float],
    geometry: Optional[dict],
    analogs: Sequence[AnalogInfo],
    size: Tuple[int, int] = (1500, 900),
) -> Optional[str]:
    """Map showing the selected lake and numbered similar-lake markers.

    Uses the exact coordinates and ranking from the Analog search results,
    with the same marker colours as the interactive map.
    """
    if not analogs:
        return None
    extent = _match_aspect(_analog_map_bbox(bbox, center, analogs), size)
    image = await _try_base(extent, size, "similar-lakes")
    draw = ImageDraw.Draw(image)
    project = _project(extent, size)

    _draw_lake_boundary(
        draw,
        project,
        geometry,
        fill=QUERY_FILL,
        fill_alpha=46,
        outline=QUERY_FILL,
    )
    center_lat, center_lon = center
    _draw_marker(
        draw,
        project,
        center_lon,
        center_lat,
        radius=13,
        fill=QUERY_FILL,
        label="★",
    )
    for analog in analogs:
        _draw_marker(
            draw,
            project,
            analog.center_lon,
            analog.center_lat,
            radius=15,
            fill=similarity_color(analog.similarity_score),
            label=str(analog.rank),
        )
    return _to_data_uri(image)
