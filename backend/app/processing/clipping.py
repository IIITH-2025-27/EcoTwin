"""Clip a Sentinel-2 GeoTIFF raster to a lake polygon boundary.

Opens the raster lazily (no full load into memory), reprojects the
polygon if needed, and returns only the clipped data within the lake
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import rasterio
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform
import pyproj
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ClippedRaster:
    """Result of clipping a raster to a polygon."""

    data: np.ndarray          # shape: (bands, height, width), float32
    transform: Any            # rasterio Affine
    crs: Any                  # rasterio CRS
    nodata: Optional[float]   # nodata sentinel value
    pixel_size_x: float       # pixel width in CRS units
    pixel_size_y: float       # pixel height in CRS units (absolute)
    band_count: int


def _reproject_geom(geom, src_crs: str, dst_crs: str):
    """Reproject a Shapely geometry between coordinate reference systems."""
    project = pyproj.Transformer.from_crs(
        src_crs, dst_crs, always_xy=True
    ).transform
    return shapely_transform(project, geom)


def clip_raster_to_polygon(
    file_path: str,
    lake_shape,
    geom_srid: int = 4326,
) -> ClippedRaster:
    """Open a GeoTIFF and clip it to the lake polygon.

    Parameters
    ----------
    file_path:
        Path to the merged Sentinel-2 GeoTIFF.
    lake_shape:
        Shapely geometry of the lake polygon (already converted
        from the PostGIS WKBElement via ``geoalchemy2.shape.to_shape``).
    geom_srid:
        SRID of the polygon geometry (default 4326).

    Returns
    -------
    ClippedRaster with the masked array and metadata.
    """
    with rasterio.open(file_path) as src:
        raster_crs = src.crs

        # Reproject polygon to raster CRS if needed
        lake_geom = lake_shape
        if raster_crs and str(raster_crs) != f"EPSG:{geom_srid}":
            logger.debug(
                "Reprojecting polygon",
                from_crs=f"EPSG:{geom_srid}",
                to_crs=str(raster_crs),
            )
            lake_geom = _reproject_geom(
                lake_geom,
                f"EPSG:{geom_srid}",
                str(raster_crs),
            )

        geojson_geom = mapping(lake_geom)

        clipped, clipped_transform = rasterio_mask(
            src,
            [geojson_geom],
            crop=True,
            nodata=src.nodata if src.nodata is not None else 0,
            filled=True,
        )

        nodata_val = src.nodata if src.nodata is not None else 0
        pixel_size_x = abs(clipped_transform.a)
        pixel_size_y = abs(clipped_transform.e)

        logger.debug(
            "Raster clipped",
            shape=clipped.shape,
            nodata=nodata_val,
            pixel_size=(pixel_size_x, pixel_size_y),
        )

        return ClippedRaster(
            data=clipped.astype(np.float32),
            transform=clipped_transform,
            crs=raster_crs,
            nodata=float(nodata_val) if nodata_val is not None else None,
            pixel_size_x=pixel_size_x,
            pixel_size_y=pixel_size_y,
            band_count=clipped.shape[0],
        )
