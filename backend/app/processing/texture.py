"""Compute GLCM (Grey-Level Co-occurrence Matrix) texture features.

Implements a pure-NumPy GLCM computation without external dependencies
like scikit-image.  The GLCM is computed on a configurable band
(default: NIR-proxy B5), quantised to configurable grey levels,
averaged over 4 orientations (0°, 45°, 90°, 135°) at a configurable
distance.

All configuration is imported from ``processing.constants``.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from app.processing.constants import (
    GLCM_BAND_INDEX,
    GLCM_DISTANCE,
    GLCM_NUM_LEVELS,
)

# Displacement vectors for 4 orientations at the configured distance
# (dy, dx): 0°, 45°, 90°, 135°
_OFFSETS = [
    (0, GLCM_DISTANCE),                   # 0° horizontal
    (-GLCM_DISTANCE, GLCM_DISTANCE),      # 45° upper-right diagonal
    (-GLCM_DISTANCE, 0),                  # 90° vertical
    (-GLCM_DISTANCE, -GLCM_DISTANCE),     # 135° upper-left diagonal
]


def _quantise(
    band: np.ndarray,
    valid_mask: np.ndarray,
    num_levels: int = GLCM_NUM_LEVELS,
) -> np.ndarray:
    """Quantise a band to [0, num_levels-1] using min-max scaling.

    Invalid pixels are set to -1.
    """
    valid_vals = band[valid_mask]
    if valid_vals.size == 0:
        return np.full(band.shape, -1, dtype=np.int32)

    vmin, vmax = float(np.min(valid_vals)), float(np.max(valid_vals))
    if vmax - vmin < 1e-10:
        # Constant image → all zeros
        quantised = np.zeros(band.shape, dtype=np.int32)
    else:
        quantised = np.clip(
            ((band - vmin) / (vmax - vmin) * (num_levels - 1)).astype(np.int32),
            0,
            num_levels - 1,
        )

    quantised[~valid_mask] = -1
    return quantised


def _compute_glcm_matrix(
    quantised: np.ndarray,
    dy: int,
    dx: int,
    num_levels: int = GLCM_NUM_LEVELS,
) -> np.ndarray:
    """Compute a normalised GLCM for one displacement vector.

    Returns a (num_levels, num_levels) float64 array that sums to 1.
    """
    h, w = quantised.shape

    # Define the overlapping regions
    if dy >= 0:
        row_start_ref, row_end_ref = 0, h - dy
        row_start_nbr, row_end_nbr = dy, h
    else:
        row_start_ref, row_end_ref = -dy, h
        row_start_nbr, row_end_nbr = 0, h + dy

    if dx >= 0:
        col_start_ref, col_end_ref = 0, w - dx
        col_start_nbr, col_end_nbr = dx, w
    else:
        col_start_ref, col_end_ref = -dx, w
        col_start_nbr, col_end_nbr = 0, w + dx

    ref = quantised[row_start_ref:row_end_ref, col_start_ref:col_end_ref]
    nbr = quantised[row_start_nbr:row_end_nbr, col_start_nbr:col_end_nbr]

    # Only count pairs where both pixels are valid
    valid_pairs = (ref >= 0) & (nbr >= 0)
    ref_valid = ref[valid_pairs]
    nbr_valid = nbr[valid_pairs]

    if ref_valid.size == 0:
        return np.zeros((num_levels, num_levels), dtype=np.float64)

    # Build co-occurrence matrix
    glcm = np.zeros((num_levels, num_levels), dtype=np.float64)
    np.add.at(glcm, (ref_valid, nbr_valid), 1)

    # Make symmetric
    glcm = glcm + glcm.T

    # Normalise
    total = glcm.sum()
    if total > 0:
        glcm /= total

    return glcm


def _glcm_properties(glcm: np.ndarray) -> Dict[str, float]:
    """Extract texture properties from a normalised GLCM.

    Returns contrast, correlation, energy, entropy, homogeneity,
    dissimilarity.
    """
    num_levels = glcm.shape[0]
    i_indices = np.arange(num_levels, dtype=np.float64)
    j_indices = np.arange(num_levels, dtype=np.float64)

    # Marginal means and stds
    px = glcm.sum(axis=1)  # row marginal
    py = glcm.sum(axis=0)  # col marginal

    mu_x = np.sum(i_indices * px)
    mu_y = np.sum(j_indices * py)
    sigma_x = np.sqrt(np.sum(((i_indices - mu_x) ** 2) * px))
    sigma_y = np.sqrt(np.sum(((j_indices - mu_y) ** 2) * py))

    # Index grids
    i_grid, j_grid = np.meshgrid(i_indices, j_indices, indexing="ij")
    diff = np.abs(i_grid - j_grid)

    # Contrast: Σ (i-j)² × P(i,j)
    contrast = float(np.sum((diff ** 2) * glcm))

    # Dissimilarity: Σ |i-j| × P(i,j)
    dissimilarity = float(np.sum(diff * glcm))

    # Homogeneity: Σ P(i,j) / (1 + (i-j)²)
    homogeneity = float(np.sum(glcm / (1.0 + diff ** 2)))

    # Energy: Σ P(i,j)²
    energy = float(np.sum(glcm ** 2))

    # Entropy: -Σ P(i,j) × log₂(P(i,j))
    nonzero = glcm[glcm > 0]
    entropy = float(-np.sum(nonzero * np.log2(nonzero)))

    # Correlation: Σ (i-μx)(j-μy)×P(i,j) / (σx×σy)
    if sigma_x > 1e-10 and sigma_y > 1e-10:
        correlation = float(
            np.sum((i_grid - mu_x) * (j_grid - mu_y) * glcm)
            / (sigma_x * sigma_y)
        )
    else:
        correlation = 0.0

    return {
        "glcm_contrast": contrast,
        "glcm_correlation": correlation,
        "glcm_energy": energy,
        "glcm_entropy": entropy,
        "glcm_homogeneity": homogeneity,
        "glcm_dissimilarity": dissimilarity,
    }


def compute_glcm_features(
    bands: np.ndarray,
    nodata: Optional[float] = None,
    band_index: int = GLCM_BAND_INDEX,
    num_levels: int = GLCM_NUM_LEVELS,
) -> Dict[str, Optional[float]]:
    """Compute GLCM texture features from a single band.

    Parameters
    ----------
    bands : (C, H, W) float32 array
    nodata : nodata sentinel value
    band_index : which band to use (default 3 = B5 / NIR proxy)
    num_levels : number of grey levels for quantisation

    Returns
    -------
    Dict with glcm_contrast, glcm_correlation, glcm_energy,
    glcm_entropy, glcm_homogeneity, glcm_dissimilarity.
    Returns None values if insufficient valid pixels.
    """
    band = bands[band_index]

    # Valid pixel mask
    if nodata is not None:
        valid = band != nodata
    else:
        valid = np.isfinite(band)

    if np.sum(valid) < 4:
        return {
            "glcm_contrast": None,
            "glcm_correlation": None,
            "glcm_energy": None,
            "glcm_entropy": None,
            "glcm_homogeneity": None,
            "glcm_dissimilarity": None,
        }

    # Quantise
    quantised = _quantise(band, valid, num_levels)

    # Compute GLCM for each orientation and average properties
    all_props: Dict[str, float] = {}
    count = 0

    for dy, dx in _OFFSETS:
        glcm = _compute_glcm_matrix(quantised, dy, dx, num_levels)
        if glcm.sum() == 0:
            continue
        props = _glcm_properties(glcm)
        for key, val in props.items():
            all_props[key] = all_props.get(key, 0.0) + val
        count += 1

    if count == 0:
        return {k: None for k in [
            "glcm_contrast", "glcm_correlation", "glcm_energy",
            "glcm_entropy", "glcm_homogeneity", "glcm_dissimilarity",
        ]}

    # Average over orientations
    return {k: round(v / count, 6) for k, v in all_props.items()}
