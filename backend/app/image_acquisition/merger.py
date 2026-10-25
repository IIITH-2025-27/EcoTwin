"""
merger.py

Merge downloaded Sentinel-2 GeoTIFF tiles into a single raster and
crop it to the buffered lake polygon.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from shapely.geometry import mapping
from app.core.config import settings
from app.ML_pipeline.constants import S2_NODATA
from rasterio.enums import Resampling
import structlog

logger = structlog.get_logger(__name__)


def set_nodata_tag(path: Path, nodata: float = S2_NODATA) -> None:
    """Write ``nodata`` into a GeoTIFF header (pixels are not touched).

    Earth Engine downloads are tagged ``nodata = 0`` although the masked
    pixels hold ``S2_NODATA``. Read with that tag, a genuine reflectance of
    0 (dark water in the NIR / red-edge bands) would count as missing.
    """
    with rasterio.open(path, "r+") as ds:
        if ds.nodata != nodata:
            ds.nodata = nodata


def mosaic_geotiffs(paths: List[Path], output_path: Path) -> Path:
    """Stitch rasters on the same pixel grid into one GeoTIFF (no overlap
    handling beyond "first valid wins"). Used to rebuild a tile that was
    downloaded in parts."""
    for p in paths:
        set_nodata_tag(p)
    datasets = [rasterio.open(p) for p in paths]
    try:
        mosaic, transform = merge(datasets, nodata=S2_NODATA)
        meta = datasets[0].meta.copy()
        meta.update(
            driver="GTiff",
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            count=mosaic.shape[0],
            dtype=mosaic.dtype,
            nodata=S2_NODATA,
            compress="DEFLATE",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(mosaic)
    finally:
        for ds in datasets:
            ds.close()
    return output_path


class TileMerger:
    """
    Merge GeoTIFF tiles into a single raster and crop
    the result to a polygon.
    """

    def merge_tiles(
        self,
        tile_paths: List[Path],
        output_path: Path,
    ) -> Path:

        if not tile_paths:
            raise ValueError("No tiles supplied for merging.")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Merging GeoTIFF tiles",
            tile_count=len(tile_paths),
            output=str(output_path),
        )

        # GEE tags its downloads nodata=0; merge() masks each source with its
        # own tag, so fix the tags first or true-zero reflectances are lost.
        for tile in tile_paths:
            set_nodata_tag(tile)

        datasets = []

        try:
            for tile in tile_paths:
                datasets.append(rasterio.open(tile))

            # Output nodata = S2_NODATA, so one tile's fill never overwrites
            # a neighbour's valid pixels where they overlap.
            mosaic, transform = merge(datasets, nodata=S2_NODATA)

            src = datasets[0]

            metadata = src.meta.copy()
            metadata.update(
                {
                    "driver": "GTiff",
                    "height": mosaic.shape[1],
                    "width": mosaic.shape[2],
                    "transform": transform,
                    "count": mosaic.shape[0],
                    "dtype": mosaic.dtype,
                    "crs": src.crs,
                    "nodata": S2_NODATA,

                    # Compression
                    "compress": "DEFLATE",
                    # "predictor": 2,
                    "zlevel": 6,

                    # Internal tiling
                    "tiled": True,
                    "blockxsize": 512,
                    "blockysize": 512,

                    # Large file support
                    "BIGTIFF": "IF_SAFER",
                }
            )

            with rasterio.open(output_path, "w", **metadata) as dst:
                dst.write(mosaic)

                # Internal overviews
                dst.build_overviews(
                    [2, 4, 8, 16],
                    Resampling.average,
                )
                dst.update_tags(
                    ns="rio_overview",
                    resampling="average",
                )

        finally:
            for ds in datasets:
                ds.close()

        logger.info(
            "Compressed merge completed",
            output=str(output_path),
            size=output_path.stat().st_size,
        )

        return output_path


    def merge_tiles_only(
        self,
        tile_paths: List[Path],
        output_path: Path,
        delete_tiles: bool = True,
    ) -> Path:

        self.merge_tiles(
            tile_paths=tile_paths,
            output_path=output_path,
        )

        if delete_tiles:
            logger.info(
                "Deleting downloaded tiles",
                tile_count=len(tile_paths),
            )

            for tile in tile_paths:
                try:
                    tile.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning(
                        "Failed to delete tile",
                        tile=str(tile),
                        error=str(exc),
                    )

        logger.info(
            "Lake GeoTIFF created",
            output=str(output_path),
        )

        return output_path