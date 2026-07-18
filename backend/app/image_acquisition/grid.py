"""
Grid generation for tile-based Sentinel-2 image acquisition.

Partitions a buffered lake polygon into fixed-size tiles (default 10 km × 10 km)
so each tile stays within GEE's ``getDownloadURL()`` size limit (~50 MB).

This module has **no GEE or database dependencies** — pure geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pyproj import Transformer
from shapely.geometry import Polygon, box
from shapely.ops import transform


@dataclass(frozen=True)
class TileInfo:
    """Metadata for a single grid tile."""

    tile_index: str  # e.g. "0_0" (col_row)
    geometry_4326: Polygon  # tile boundary in EPSG:4326
    bbox: tuple  # (west, south, east, north) in EPSG:4326


def generate_tile_grid(
    buffered_geom_4326: Polygon,
    tile_size_m: int,
    projected_crs: int = 6933,
) -> List[TileInfo]:
    """
    Partition a buffered polygon into a grid of tiles.

    Steps:
      1. Project ``buffered_geom_4326`` to ``projected_crs`` (equal-area).
      2. Compute the bounding box in projected coordinates.
      3. Generate a regular grid of ``tile_size_m × tile_size_m`` cells.
      4. Keep only cells that **intersect** the projected buffered polygon.
      5. Reproject each intersecting tile back to EPSG:4326.

    Args:
        buffered_geom_4326: The buffered lake polygon in EPSG:4326.
        tile_size_m: Side length of each tile in metres.
        projected_crs: EPSG code for the projected CRS used for
                       grid generation (default: 6933 — equal-area cylindrical).

    Returns:
        List of ``TileInfo`` objects for tiles that intersect the buffered polygon.
    """
    # ── Step 1: Project to equal-area CRS ──────────────────────────────────
    to_projected = Transformer.from_crs(
        4326, projected_crs, always_xy=True
    ).transform
    projected_geom = transform(to_projected, buffered_geom_4326)

    # ── Step 2: Bounding box in projected coordinates ──────────────────────
    minx, miny, maxx, maxy = projected_geom.bounds

    # ── Step 3–4: Generate grid and filter by intersection ─────────────────
    to_4326 = Transformer.from_crs(
        projected_crs, 4326, always_xy=True
    ).transform

    tiles: List[TileInfo] = []
    col = 0
    x = minx
    while x < maxx:
        row = 0
        y = miny
        while y < maxy:
            # Create tile cell in projected CRS
            cell = box(x, y, x + tile_size_m, y + tile_size_m)

            if cell.intersects(projected_geom):
                # Reproject tile to EPSG:4326
                cell_4326 = transform(to_4326, cell)
                tile_bounds = cell_4326.bounds  # (minx, miny, maxx, maxy)

                tiles.append(
                    TileInfo(
                        tile_index=f"{col}_{row}",
                        geometry_4326=cell_4326,
                        bbox=(
                            tile_bounds[0],  # west
                            tile_bounds[1],  # south
                            tile_bounds[2],  # east
                            tile_bounds[3],  # north
                        ),
                    )
                )
            row += 1
            y += tile_size_m

        col += 1
        x += tile_size_m

    return tiles
