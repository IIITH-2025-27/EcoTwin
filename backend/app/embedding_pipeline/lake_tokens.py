"""
Lake / shore token windows for Prithvi.

For one lake-year GeoTIFF (30 m, S2_BANDS_DOWNLOAD stack) this builds:

  * the lake region   — pixels whose centre lies inside the lake polygon
  * the shore region  — pixels within ``shore_ring_m`` outside the polygon

and tiles their joint extent into 224 × 224 px windows (Prithvi's input
size, 6.72 km at 30 m). Each window is a 14 × 14 grid of 16 px tokens
(480 m). For every token it records the fraction of its pixels that are
lake, shore, and valid (not nodata); only tokens touching the lake or the
shore are later fed to the encoder.

Windows are laid out on the token grid of the raster, which itself sits on
Earth Engine's fixed global 30 m grid, so a lake gets identical windows and
tokens in every year.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

import numpy as np
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform

from app.embedding_pipeline.config import EmbeddingPipelineConfig
from app.ML_pipeline.constants import PRITHVI_BAND_INDICES, S2_BANDS_DOWNLOAD


@dataclass
class TokenWindow:
    """One 224 × 224 px encoder window and the tokens to encode from it."""

    data: np.ndarray          # (6, H, W) float32, normalised Prithvi input
    keep_idx: np.ndarray      # (K,) int64 token indices (row-major) to encode
    lake_frac: np.ndarray     # (K,) fraction of token pixels that are valid lake
    shore_frac: np.ndarray    # (K,) fraction of token pixels that are valid shore
    valid_frac: np.ndarray    # (K,) fraction of token pixels that are valid


@dataclass
class LakeTokens:
    """All encoder windows for one lake-year plus pixel bookkeeping."""

    windows: List[TokenWindow]
    lake_pixels: int          # lake pixels in the raster (by polygon)
    valid_lake_pixels: int    # of those, not nodata
    shore_pixels: int
    valid_shore_pixels: int


def check_band_stack(geotiff_path: str) -> None:
    """Raise if the GeoTIFF is not the current S2_BANDS_DOWNLOAD stack.

    Older merged images hold only B2-B7 at 10 m, which lack the narrow NIR
    and SWIR bands Prithvi needs, so they cannot produce valid embeddings.
    """
    import rasterio  # noqa: PLC0415

    with rasterio.open(geotiff_path) as src:
        count = src.count
    if count != len(S2_BANDS_DOWNLOAD):
        raise ValueError(
            f"{geotiff_path}: expected {len(S2_BANDS_DOWNLOAD)}-band stack "
            f"{S2_BANDS_DOWNLOAD}, got {count} bands — re-download imagery "
            "with the current band set"
        )


def _shore_outer_polygon(lake_polygon_4326, ring_m: int, projected_crs: int):
    """Lake polygon buffered outward by ``ring_m`` metres (EPSG:4326)."""
    to_proj = Transformer.from_crs(4326, projected_crs, always_xy=True).transform
    to_4326 = Transformer.from_crs(projected_crs, 4326, always_xy=True).transform
    return shapely_transform(
        to_4326, shapely_transform(to_proj, lake_polygon_4326).buffer(ring_m)
    )


def build_lake_tokens(
    geotiff_path: str,
    lake_polygon_4326,
    config: EmbeddingPipelineConfig,
) -> LakeTokens:
    """Build the encoder windows for one lake-year. See module docstring."""
    import rasterio  # noqa: PLC0415
    from rasterio.features import rasterize  # noqa: PLC0415
    from rasterio.windows import Window, from_bounds  # noqa: PLC0415

    win = config.window_px
    tok = config.token_px
    grid = win // tok
    band_mean = np.asarray(config.band_mean, dtype=np.float32)[:, None, None]
    band_std = np.asarray(config.band_std, dtype=np.float32)[:, None, None]

    outer = _shore_outer_polygon(
        lake_polygon_4326, config.shore_ring_m, config.projected_crs
    )

    with rasterio.open(geotiff_path) as src:
        if str(src.crs) != "EPSG:4326":
            raise ValueError(f"{geotiff_path}: expected EPSG:4326, got {src.crs}")
        nodata = src.nodata

        # Pixel extent of lake + shore, snapped outward to whole tokens of
        # the raster's own grid, then padded to whole windows and centred.
        roi = from_bounds(*outer.bounds, transform=src.transform)
        r0 = math.floor(roi.row_off / tok) * tok
        c0 = math.floor(roi.col_off / tok) * tok
        r1 = math.ceil((roi.row_off + roi.height) / tok) * tok
        c1 = math.ceil((roi.col_off + roi.width) / tok) * tok
        n_wr = max(1, math.ceil((r1 - r0) / win))
        n_wc = max(1, math.ceil((c1 - c0) / win))
        # Centre the window block on the region (in whole tokens)
        r0 -= ((n_wr * win - (r1 - r0)) // (2 * tok)) * tok
        c0 -= ((n_wc * win - (c1 - c0)) // (2 * tok)) * tok
        H, W = n_wr * win, n_wc * win
        window = Window(c0, r0, W, H)

        data = src.read(
            [i + 1 for i in PRITHVI_BAND_INDICES],
            window=window,
            boundless=True,
            fill_value=nodata if nodata is not None else 0,
        ).astype(np.float32)
        win_transform = src.window_transform(window)

    lake_mask = rasterize(
        [(mapping(lake_polygon_4326), 1)], out_shape=(H, W),
        transform=win_transform, fill=0, dtype="uint8",
    ).astype(bool)
    outer_mask = rasterize(
        [(mapping(outer), 1)], out_shape=(H, W),
        transform=win_transform, fill=0, dtype="uint8",
    ).astype(bool)
    shore_mask = outer_mask & ~lake_mask

    if nodata is not None:
        valid = ~np.any(data == nodata, axis=0)
    else:
        valid = np.all(np.isfinite(data), axis=0)

    # Invalid pixels → band training mean (0 after normalisation), as in
    # Prithvi's own inference.py; then normalise.
    data = np.where(valid[None], data, band_mean)
    data = (data - band_mean) / band_std

    windows: List[TokenWindow] = []
    for wr in range(n_wr):
        for wc in range(n_wc):
            rs, cs = wr * win, wc * win

            def token_frac(mask: np.ndarray) -> np.ndarray:
                block = mask[rs:rs + win, cs:cs + win]
                return block.reshape(grid, tok, grid, tok).mean(axis=(1, 3)).ravel()

            # Pooling weights count only valid (cloud-free) pixels
            lake_f = token_frac(lake_mask & valid)
            shore_f = token_frac(shore_mask & valid)
            valid_f = token_frac(valid)
            # Only tokens with valid lake or shore pixels are encoded
            keep = np.flatnonzero((lake_f + shore_f) > 0)
            if keep.size == 0:
                continue
            windows.append(TokenWindow(
                data=np.ascontiguousarray(data[:, rs:rs + win, cs:cs + win]),
                keep_idx=keep.astype(np.int64),
                lake_frac=lake_f[keep].astype(np.float32),
                shore_frac=shore_f[keep].astype(np.float32),
                valid_frac=valid_f[keep].astype(np.float32),
            ))

    return LakeTokens(
        windows=windows,
        lake_pixels=int(lake_mask.sum()),
        valid_lake_pixels=int((lake_mask & valid).sum()),
        shore_pixels=int(shore_mask.sum()),
        valid_shore_pixels=int((shore_mask & valid).sum()),
    )
