"""
Phase 3 — Ecosystem classification.

Two classification strategies are supported and selected automatically:

  Stage A — Rule-based (default, zero extra dependencies)
      Applies threshold rules over NDVI / NDWI / NBR means in priority
      order (most specific class first).  Works immediately after Phase 1
      ingest; confidence is a heuristic margin from the nearest boundary.

  Stage B — Learned linear probe (opt-in)
      Uses a serialised sklearn (or compatible) model stored at
      ``CLASSIFIER_MODEL_PATH`` (env var).  The model is called with the
      768-dim Prithvi embedding and must expose ``predict()`` and
      ``predict_proba()``.  Stage B is activated automatically when
      ``CLASSIFIER_MODEL_PATH`` is set AND a valid embedding is supplied.
      Falls back to Stage A on any error.

Nothing in this module touches the database.
"""

from __future__ import annotations

import os
import pickle
from typing import Optional, Tuple

import numpy as np
import structlog

from app.ML_pipeline.constants import (
    ECOSYSTEM_BARREN_NDVI_MAX,
    ECOSYSTEM_BURNED_NBR_MAX,
    ECOSYSTEM_CROPLAND_NDVI_MIN,
    ECOSYSTEM_CROPLAND_NDWI_MAX,
    ECOSYSTEM_DENSE_FOREST_NDVI_MIN,
    ECOSYSTEM_GRASSLAND_NDVI_MIN,
    ECOSYSTEM_MIN_CONFIDENCE,
    ECOSYSTEM_OPEN_FOREST_NDVI_MIN,
    ECOSYSTEM_WETLAND_NDWI_MIN,
)

logger = structlog.get_logger(__name__)

# Optional path to a serialised sklearn / compatible classification head.
# Set via CLASSIFIER_MODEL_PATH environment variable.
_CLASSIFIER_MODEL_PATH: str = os.environ.get("CLASSIFIER_MODEL_PATH", "")

# Module-level model cache — loaded once per worker process
_classifier_model = None


# ── Stage A: Rule-based classifier ────────────────────────────────────────────

def classify_by_rules(
    ndvi_mean: float,
    ndwi_mean: float,
    nbr_mean: float,
) -> Tuple[str, float]:
    """
    Classify a region by applying threshold rules to annual index means.

    Rules are evaluated in priority order (most-specific first) to avoid
    overlap.  Confidence is a simple heuristic: the normalised distance
    from the dominant threshold boundary, clamped to [ECOSYSTEM_MIN_CONFIDENCE, 1.0].

    Args:
        ndvi_mean: Annual mean NDVI for the region.
        ndwi_mean: Annual mean NDWI for the region.
        nbr_mean:  Annual mean NBR  for the region.

    Returns:
        (ecosystem_label, confidence_score)
    """

    def _clamp(v: float) -> float:
        return float(np.clip(v, ECOSYSTEM_MIN_CONFIDENCE, 1.0))

    # ── 1. Burned / severely disturbed ────────────────────────────
    if nbr_mean < ECOSYSTEM_BURNED_NBR_MAX:
        confidence = _clamp(abs(nbr_mean - ECOSYSTEM_BURNED_NBR_MAX) * 5)
        return "burned_disturbed", confidence

    # ── 2. Open water / wetland ────────────────────────────────────
    if ndwi_mean > ECOSYSTEM_WETLAND_NDWI_MIN:
        confidence = _clamp((ndwi_mean - ECOSYSTEM_WETLAND_NDWI_MIN) * 4)
        return "wetland_water", confidence

    # ── 3. Dense forest ────────────────────────────────────────────
    if ndvi_mean >= ECOSYSTEM_DENSE_FOREST_NDVI_MIN:
        confidence = _clamp((ndvi_mean - ECOSYSTEM_DENSE_FOREST_NDVI_MIN) * 4)
        return "dense_forest", confidence

    # ── 4. Open forest / woodland ──────────────────────────────────
    if ndvi_mean >= ECOSYSTEM_OPEN_FOREST_NDVI_MIN:
        confidence = _clamp(0.60 + (ndvi_mean - ECOSYSTEM_OPEN_FOREST_NDVI_MIN) * 2)
        return "open_forest", confidence

    # ── 5. Grassland / shrubland ───────────────────────────────────
    if ndvi_mean >= ECOSYSTEM_GRASSLAND_NDVI_MIN:
        confidence = _clamp(0.55 + (ndvi_mean - ECOSYSTEM_GRASSLAND_NDVI_MIN) * 2)
        return "grassland_shrub", confidence

    # ── 6. Cropland (moderate NDVI, low NDWI indicating dry farming) ─
    if ECOSYSTEM_CROPLAND_NDVI_MIN <= ndvi_mean < ECOSYSTEM_GRASSLAND_NDVI_MIN:
        if ndwi_mean < ECOSYSTEM_CROPLAND_NDWI_MAX:
            return "cropland", _clamp(0.55)

    # ── 7. Barren / urban ──────────────────────────────────────────
    if ndvi_mean < ECOSYSTEM_BARREN_NDVI_MAX:
        confidence = _clamp((ECOSYSTEM_BARREN_NDVI_MAX - ndvi_mean) * 8)
        return "barren_urban", confidence

    # ── 8. Mixed / unclassified ────────────────────────────────────
    return "mixed_vegetation", ECOSYSTEM_MIN_CONFIDENCE


# ── Stage B: Learned model (optional) ─────────────────────────────────────────

def _load_classifier():
    """Lazy-load the serialised sklearn classifier; cached per process."""
    global _classifier_model
    if _classifier_model is not None:
        return _classifier_model

    if not _CLASSIFIER_MODEL_PATH:
        return None

    try:
        with open(_CLASSIFIER_MODEL_PATH, "rb") as fh:
            _classifier_model = pickle.load(fh)
        logger.info("Ecosystem classifier loaded", path=_CLASSIFIER_MODEL_PATH)
        return _classifier_model
    except Exception as exc:
        logger.warning(
            "Could not load classifier model — falling back to rules",
            path=_CLASSIFIER_MODEL_PATH,
            error=str(exc),
        )
        return None


def _classify_by_model(embedding: list) -> Tuple[str, float]:
    """
    Call the serialised sklearn (or compatible) classifier.

    The model must implement:
        predict(X)       → array of label strings
        predict_proba(X) → (n_samples, n_classes) probability matrix

    Args:
        embedding: List of 768 floats (Prithvi output).

    Returns:
        (ecosystem_label, confidence_score)
    """
    model = _load_classifier()
    if model is None:
        raise RuntimeError("No classifier model loaded")

    vec   = np.array(embedding, dtype=np.float32).reshape(1, -1)
    label = str(model.predict(vec)[0])
    proba = float(model.predict_proba(vec).max())
    return label, proba


# ── Public entry point ─────────────────────────────────────────────────────────

def classify_region(
    ndvi_mean: float,
    ndwi_mean: float,
    nbr_mean: float,
    embedding: Optional[list] = None,
) -> Tuple[str, float]:
    """
    Classify a region into an ecosystem label with confidence score.

    Prefers the learned model when ``CLASSIFIER_MODEL_PATH`` is set AND a
    valid embedding is provided; otherwise uses rule-based classification.

    Args:
        ndvi_mean: Annual mean NDVI.
        ndwi_mean: Annual mean NDWI.
        nbr_mean:  Annual mean NBR.
        embedding: Optional 768-dim Prithvi embedding (enables Stage B).

    Returns:
        (ecosystem_label, confidence_score) where confidence ∈ [0, 1].
    """
    if _CLASSIFIER_MODEL_PATH and embedding is not None:
        try:
            label, confidence = _classify_by_model(embedding)
            logger.debug(
                "Region classified via learned model",
                label=label,
                confidence=confidence,
            )
            return label, confidence
        except Exception as exc:
            logger.warning(
                "Learned classifier failed — falling back to rule-based",
                error=str(exc),
            )

    label, confidence = classify_by_rules(ndvi_mean, ndwi_mean, nbr_mean)
    logger.debug(
        "Region classified via rules",
        label=label,
        confidence=round(confidence, 3),
        ndvi=round(ndvi_mean, 4),
        ndwi=round(ndwi_mean, 4),
        nbr=round(nbr_mean, 4),
    )
    return label, confidence
