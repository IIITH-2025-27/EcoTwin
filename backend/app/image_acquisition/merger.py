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
import structlog

logger = structlog.get_logger(__name__)


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
        """
        Merge GeoTIFF tiles.

        Parameters
        ----------
        tile_paths
            List of downloaded tile paths.

        output_path
            Output merged GeoTIFF.

        Returns
        -------
        Path
            Path to merged raster.
        """

        if not tile_paths:
            raise ValueError("No tiles supplied for merging.")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Merging GeoTIFF tiles",
            tile_count=len(tile_paths),
            output=str(output_path),
        )

        datasets = []

        try:
            for tile in tile_paths:
                datasets.append(rasterio.open(tile))

            mosaic, transform = merge(datasets)

            metadata = datasets[0].meta.copy()

            metadata.update(
                {
                    "driver": "GTiff",
                    "height": mosaic.shape[1],
                    "width": mosaic.shape[2],
                    "transform": transform,
                    "count": mosaic.shape[0],
                }
            )

            with rasterio.open(output_path, "w", **metadata) as dest:
                dest.write(mosaic)

        finally:
            for ds in datasets:
                ds.close()

        logger.info(
            "Merge completed",
            output=str(output_path),
        )

        return output_path

    def crop_to_polygon(
        self,
        merged_raster: Path,
        polygon,
        output_path: Path,
    ) -> Path:
        """
        Crop a merged raster to a polygon.

        Parameters
        ----------
        merged_raster
            Merged GeoTIFF.

        polygon
            Original lake polygon. The configured imagery buffer
            (LAKE_IMAGERY_BUFFER_METRES) is applied automatically
            before cropping.

        output_path
            Output cropped GeoTIFF.

        Returns
        -------
        Path
            Cropped raster.
        """

        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Cropping merged raster",
            raster=str(merged_raster),
            buffer_metres=settings.LAKE_IMAGERY_BUFFER_METRES,
        )

        with rasterio.open(merged_raster) as src:
            # Buffer the original lake polygon
            buffered_polygon = polygon.buffer(settings.LAKE_IMAGERY_BUFFER_METRES)

            cropped, transform = mask(
                src,
                [mapping(buffered_polygon)],
                crop=True,
            )
            metadata = src.meta.copy()
            metadata.update(
                {
                    "driver": "GTiff",
                    "height": cropped.shape[1],
                    "width": cropped.shape[2],
                    "transform": transform,
                }
            )

            with rasterio.open(output_path, "w", **metadata) as dest:
                dest.write(cropped)

        logger.info(
            "Crop completed",
            output=str(output_path),
        )

        return output_path

    def merge_and_crop(
        self,
        tile_paths: List[Path],
        polygon,
        output_path: Path,
        delete_tiles: bool = True,
    ) -> Path:
        """
        Merge tiles and crop directly to the polygon.

        Parameters
        ----------
        tile_paths
            Downloaded tile GeoTIFFs.

        polygon
            Original lake polygon. The configured imagery buffer
            (LAKE_IMAGERY_BUFFER_METRES) is applied automatically
            before cropping.

        output_path
            Final output GeoTIFF.

        Returns
        -------
        Path
            Final cropped raster.
        """

        temp_path = output_path.with_name(
            output_path.stem + "_merged.tif"
        )

        self.merge_tiles(
            tile_paths=tile_paths,
            output_path=temp_path,
        )

        self.crop_to_polygon(
            merged_raster=temp_path,
            polygon=polygon,
            output_path=output_path,
        )

        # Remove temporary merged raster
        temp_path.unlink(missing_ok=True)

        # Remove downloaded tiles
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