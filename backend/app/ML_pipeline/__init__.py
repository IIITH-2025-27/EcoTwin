"""
app.ML_pipeline
───────────────
Shared ML building blocks for EcoTwin.

  constants.py          — band sets, GEE / Prithvi / pipeline constants
  gee_init.py           — one-time Earth Engine initialisation
  _prithvi_model.py     — PrithviEncoder wrapper (incl. token-subset encoding)
  prithvi_inference.py  — process-wide Prithvi encoder singleton

The embedding pipeline itself lives in ``app.embedding_pipeline``.
"""
