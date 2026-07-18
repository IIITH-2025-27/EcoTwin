"""
1 km × 1 km grid generator for lake GeoTIFFs.

Produces a list of valid grid cells that overlap the lake polygon above
a configurable coverage threshold.  Cell geometry and rasterio read
windows are computed so the cell extractor can crop directly from the
GeoTIFF without creating temporary files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import structlog
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform

from app.embedding_pipeline.config import EmbeddingPipelineConfig

logger = structlog.get_logger(__name__)


@dataclass
class GridCell:
    """A single 1 km × 1 km grid cell with lake coverage metadata."""

    cell_number: int
    bounds_projected: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy)
    bounds_4326: Tuple[float, float, float, float]
    center_lat: float
    center_lon: float
    coverage_percent: float
    # Pixel coordinates within the source GeoTIFF (col_off, row_off, width, height)
    pixel_window: Optional[Tuple[int, int, int, int]] = None


class GridGenerator:
    """Generate a grid of 1 km cells and compute lake coverage for each."""

    def __init__(self, config: EmbeddingPipelineConfig) -> None:
        self._cfg = config

    def generate(
        self,
        geotiff_path: str,
        lake_polygon_4326,
    ) -> List[GridCell]:
        """
        Generate grid cells covering the GeoTIFF extent, filter by lake coverage.

        Args:
            geotiff_path:      Path to the buffered GeoTIFF on disk.
            lake_polygon_4326: Shapely geometry of the lake polygon (EPSG:4326).

        Returns:
            List of GridCell objects with coverage ≥ min_coverage_pct.
        """
        import rasterio  # noqa: PLC0415

        log = logger.bind(geotiff=str(geotiff_path))
        log.info("Grid generation started")

        with rasterio.open(geotiff_path) as src:
            tiff_bounds = src.bounds  # (left, bottom, right, top)
            tiff_crs = src.crs
            tiff_transform = src.transform
            tiff_width = src.width
            tiff_height = src.height

        log.info(
            "GeoTIFF metadata",
            crs=str(tiff_crs),
            bounds=tiff_bounds,
            width=tiff_width,
            height=tiff_height,
        )

        proj_crs = self._cfg.projected_crs
        cell_size = self._cfg.cell_size_m
        min_cov = self._cfg.min_coverage_pct

        # ── Transform GeoTIFF bounds to projected CRS ────────────────────
        # GeoTIFFs are typically in EPSG:4326 from GEE export
        to_proj = Transformer.from_crs(
            tiff_crs.to_epsg() or 4326, proj_crs, always_xy=True
        ).transform
        from_proj = Transformer.from_crs(
            proj_crs, 4326, always_xy=True
        ).transform

        # Transform the four corners to get projected extent
        proj_minx, proj_miny = to_proj(tiff_bounds.left, tiff_bounds.bottom)
        proj_maxx, proj_maxy = to_proj(tiff_bounds.right, tiff_bounds.top)

        # Ensure correct ordering
        proj_minx, proj_maxx = min(proj_minx, proj_maxx), max(proj_minx, proj_maxx)
        proj_miny, proj_maxy = min(proj_miny, proj_maxy), max(proj_miny, proj_maxy)

        # ── Transform lake polygon to projected CRS ──────────────────────
        lake_proj = transform(to_proj, lake_polygon_4326)

        # ── Generate grid cells ──────────────────────────────────────────
        cols = int(np.ceil((proj_maxx - proj_minx) / cell_size))
        rows = int(np.ceil((proj_maxy - proj_miny) / cell_size))
        total_cells = cols * rows

        log.info(
            "Grid dimensions",
            cols=cols,
            rows=rows,
            total_cells=total_cells,
            cell_size_m=cell_size,
        )

        valid_cells: List[GridCell] = []
        cell_number = 0

        for row in range(rows):
            for col in range(cols):
                # Cell bounds in projected CRS
                cx_min = proj_minx + col * cell_size
                cy_min = proj_miny + row * cell_size
                cx_max = cx_min + cell_size
                cy_max = cy_min + cell_size

                cell_box_proj = box(cx_min, cy_min, cx_max, cy_max)

                # Compute intersection with lake polygon
                if not cell_box_proj.intersects(lake_proj):
                    cell_number += 1
                    continue

                intersection = cell_box_proj.intersection(lake_proj)
                coverage = (intersection.area / cell_box_proj.area) * 100.0

                if coverage < min_cov:
                    cell_number += 1
                    continue

                # Convert cell bounds back to EPSG:4326
                lon_min, lat_min = from_proj(cx_min, cy_min)
                lon_max, lat_max = from_proj(cx_max, cy_max)
                center_lon = (lon_min + lon_max) / 2
                center_lat = (lat_min + lat_max) / 2

                # Compute pixel window in the GeoTIFF
                pixel_window = self._compute_pixel_window(
                    tiff_transform, tiff_width, tiff_height,
                    lon_min, lat_min, lon_max, lat_max,
                )

                if pixel_window is None:
                    cell_number += 1
                    continue

                valid_cells.append(
                    GridCell(
                        cell_number=cell_number,
                        bounds_projected=(cx_min, cy_min, cx_max, cy_max),
                        bounds_4326=(lon_min, lat_min, lon_max, lat_max),
                        center_lat=center_lat,
                        center_lon=center_lon,
                        coverage_percent=round(coverage, 2),
                        pixel_window=pixel_window,
                    )
                )
                cell_number += 1

        log.info(
            "Grid generation completed",
            total_cells=total_cells,
            valid_cells=len(valid_cells),
            min_coverage_pct=min_cov,
        )
        return valid_cells

    @staticmethod
    def _compute_pixel_window(
        tiff_transform,
        tiff_width: int,
        tiff_height: int,
        lon_min: float,
        lat_min: float,
        lon_max: float,
        lat_max: float,
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Convert geographic bounds to pixel coordinates (col_off, row_off, width, height).

        Returns None if the window falls entirely outside the GeoTIFF.
        """
        from rasterio.transform import rowcol  # noqa: PLC0415

        # rasterio rowcol: (transform, ys, xs) → (rows, cols)
        row_min, col_min = rowcol(tiff_transform, lon_min, lat_max)
        row_max, col_max = rowcol(tiff_transform, lon_max, lat_min)

        # Ensure correct ordering
        row_min, row_max = min(row_min, row_max), max(row_min, row_max)
        col_min, col_max = min(col_min, col_max), max(col_min, col_max)

        # Clip to GeoTIFF bounds
        col_off = max(0, col_min)
        row_off = max(0, row_min)
        col_end = min(tiff_width, col_max)
        row_end = min(tiff_height, row_max)

        width = col_end - col_off
        height = row_end - row_off

        if width <= 0 or height <= 0:
            return None

        return (col_off, row_off, width, height)
