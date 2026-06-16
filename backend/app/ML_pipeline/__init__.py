"""
app.ML_pipeline
───────────────
Three-phase data ingestion and ML inference pipeline for EcoTwin.

Phases
------
1. GEE ingest   (gee_ingest.py)         — Sentinel-2 → NDVI/NDWI/NBR stats
2. Prithvi      (prithvi_inference.py)  — 768-dim embedding via Prithvi-100M
3. Classification (classifier.py)       — ecosystem label from rules or model

Celery tasks and orchestration live in pipeline.py.
All tuneable constants are in constants.py.
"""
