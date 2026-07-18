"""
Cell extractor — crops individual grid cells from a GeoTIFF.

Reads cell data directly into memory via rasterio windowed reads (no
temporary files on disk).  Applies Prithvi per-band normalisation and
resizes to the model's expected patch size.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import numpy as np
import structlog

from app.embedding_pipeline.config import EmbeddingPipelineConfig
from app.embedding_pipeline.grid_generator import GridCell

logger = structlog.get_logger(__name__)


class CellExtractor:
    """Extract and preprocess grid cells from a GeoTIFF for Prithvi inference."""

    def __init__(self, config: EmbeddingPipelineConfig) -> None:
        self._cfg = config
        self._band_mean = np.array(config.band_mean, dtype=np.float32)
        self._band_std = np.array(config.band_std, dtype=np.float32)

    def extract_cell(
        self,
        geotiff_path: str,
        cell: GridCell,
    ) -> Optional[np.ndarray]:
        """
        Read a single cell from the GeoTIFF, normalise, and resize.

        Args:
            geotiff_path: Path to the source GeoTIFF.
            cell:         GridCell with pixel_window coordinates.

        Returns:
            (C, H, W) float32 array ready for Prithvi, or None on failure.
        """
        import rasterio  # noqa: PLC0415
        from rasterio.windows import Window  # noqa: PLC0415

        if cell.pixel_window is None:
            return None

        col_off, row_off, width, height = cell.pixel_window

        try:
            with rasterio.open(geotiff_path) as src:
                window = Window(col_off, row_off, width, height)
                # Read all bands → (C, H, W)
                data = src.read(window=window).astype(np.float32)

            if data.size == 0 or data.shape[0] == 0:
                logger.warning(
                    "Empty cell data", cell_number=cell.cell_number
                )
                return None

            # Per-band normalisation: (x - mean) / std
            # band_mean/std shape: (C,) → broadcast over (C, H, W)
            num_bands = min(data.shape[0], len(self._band_mean))
            for b in range(num_bands):
                data[b] = (data[b] - self._band_mean[b]) / self._band_std[b]

            # Resize to model input size
            target = self._cfg.patch_size_px
            data = self._resize(data, target)

            return data

        except Exception as exc:
            logger.warning(
                "Cell extraction failed",
                cell_number=cell.cell_number,
                error=str(exc),
            )
            return None

    def extract_batch(
        self,
        geotiff_path: str,
        cells: List[GridCell],
    ) -> List[Optional[np.ndarray]]:
        """
        Extract multiple cells in parallel using a thread pool.

        Returns a list aligned with the input cells. Failed cells are None.
        """
        max_workers = min(self._cfg.max_workers, len(cells))

        if max_workers <= 1:
            return [self.extract_cell(geotiff_path, c) for c in cells]

        results: List[Optional[np.ndarray]] = [None] * len(cells)

        def _worker(idx: int, cell: GridCell) -> tuple:
            return idx, self.extract_cell(geotiff_path, cell)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_worker, i, cell)
                for i, cell in enumerate(cells)
            ]
            for future in futures:
                idx, arr = future.result()
                results[idx] = arr

        extracted = sum(1 for r in results if r is not None)
        logger.info(
            "Batch extraction completed",
            total=len(cells),
            extracted=extracted,
            failed=len(cells) - extracted,
        )
        return results

    @staticmethod
    def _resize(arr: np.ndarray, target: int) -> np.ndarray:
        """Resize a (C, H, W) array to (C, target, target)."""
        if arr.shape[1] == target and arr.shape[2] == target:
            return arr

        try:
            import cv2  # noqa: PLC0415

            return np.stack(
                [
                    cv2.resize(
                        arr[c], (target, target),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    for c in range(arr.shape[0])
                ],
                axis=0,
            )
        except ImportError:
            # Fallback: crop or zero-pad
            c, h, w = arr.shape
            out = np.zeros((c, target, target), dtype=arr.dtype)
            ch, cw = min(h, target), min(w, target)
            out[:, :ch, :cw] = arr[:, :ch, :cw]
            return out
