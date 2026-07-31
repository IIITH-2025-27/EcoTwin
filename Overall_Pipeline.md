# EcoTwin — Pipeline Documentation

## What is EcoTwin?

EcoTwin is an AI-powered ecosystem analog search and forecasting system.
It uses geospatial foundation model (Prithvi) embeddings to find historically similar lake ecosystems ("analogs") and uses their future trajectories to forecast what a query lake's ecosystem will look like in coming years.

---

## What Has Been Implemented

### Stage 1 — Satellite Image Ingestion

- Satellite imagery for lake regions is acquired and stored.
- Each lake region has one image snapshot per year.

### Stage 2 — Embedding Generation (Prithvi Foundation Model)

- The Prithvi geospatial foundation model processes each yearly satellite image.
- It produces a high-dimensional embedding vector that encodes the structural and spectral characteristics of the ecosystem for that year.
- These embeddings are stored in PostgreSQL with pgvector support, indexed by `(lake_id, year)`.

### Stage 3 — Embedding Storage & Database

- Every lake region has a time-series of embeddings — one vector per year.
- The database schema captures `region_id`, `lake_id`, `year`, `center_lat`, `center_lon`, and the `embedding` vector.
- pgvector is enabled for future ANN (approximate nearest-neighbour) search support.

### Stage 4 — Similarity Search (Analog Search)

- Given a query lake and an anchor year, the system builds a **5-year query trajectory** (the 5 most recent yearly embeddings up to that anchor year).
- It fetches all other lakes' full embedding histories as the candidate pool.
- For each candidate lake, all possible 5-year sliding windows are generated and compared against the query trajectory.
- The best-matching window per candidate lake is scored using one of three methods:
  - **Cosine similarity** — angle between embedding vectors
  - **Euclidean distance** — spatial proximity of vectors
  - **KNN inner product** — inner product similarity
- All candidates are ranked by score and the top-K analogs are returned.

### Stage 5 — Analog Forecasting (Embedding-Level)

- The top-K analog lakes are filtered: only analogs whose embedding history has **enough future data** after their matched window are kept.
- Each valid analog is assigned a weight based on its similarity score (normalised so weights sum to 1).
- For each forecast horizon year (e.g. +1, +2, +3 years), the system takes the actual future embeddings of each valid analog lake at that offset and computes a **weighted average** across all analogs.
- This produces one **forecast embedding vector per future year** — a synthetic representation of where the query ecosystem is likely to be heading.
- The overall confidence score is computed from the weighted-mean similarity, then calibrated per similarity method, and decays slightly for each year further into the future.

### Stage 6 — API & Frontend (Forecast Response)

- The backend returns a `ForecastResponse` containing:
  - The best analog match (lake ID + matched year window)
  - Per-year forecast horizons with confidence scores
  - Vegetation, water, and burn severity trend labels (currently placeholder values)
  - A human-readable explanation of which analogs were used
- The frontend displays this response via the `useForecast` React hook.
- Results are cached in Redis to avoid recomputation.

---

## Current Limitation

The forecast **embedding vectors** for each future year are fully computed and available internally.
However, the spectral indicator values (`NDVI`, `NDWI`, `NBR`) shown per forecast year are currently set to `0.0`.

This is because the **decoder** — the component that translates an embedding vector back into interpretable spectral indices — has not yet been integrated. This is the next major step.

---

## What Needs to Be Done Next

### Step 1 — Design / Select a Decoder

- Decide on the decoder approach:
  - A **learned decoder** (e.g. a small neural network or regression model) trained to map Prithvi embedding vectors → NDVI / NDWI / NBR values.
  - Or a **lookup / interpolation** approach using the existing ground-truth embeddings and their known spectral values as reference points.
- Gather paired training data: embedding vectors alongside their ground-truth NDVI, NDWI, and NBR values for the same lake-year combinations.

### Step 2 — Train the Decoder

- Train the decoder on historical embedding–spectral pairs.
- Validate that it accurately reconstructs spectral values for held-out years and lakes.
- Save the trained decoder model weights for inference.

### Step 3 — Integrate the Decoder into the Backend

- Expose the computed forecast embedding vectors from the forecasting module through the API response schema.
- Load the decoder model at server startup.
- For each forecast horizon year, pass the forecast embedding through the decoder to produce predicted NDVI, NDWI, and NBR values.
- Replace the current `0.0` placeholders with these decoded values.

### Step 4 — Derive Trend Labels

- Use the decoded spectral values across the forecast years to compute trend directions (improving / stable / degrading) for vegetation health, water extent, and burn severity.
- Replace the current hardcoded `"stable"` trend placeholders with these data-driven labels.

### Step 5 — Frontend Integration

- Update the UI to display the decoded NDVI, NDWI, and NBR forecast values as charts or indicators per horizon year.
- Surface the trend labels visually (e.g. colour-coded arrows or badges).

### Step 6 — Validation & Evaluation

- Backtest the full pipeline: pick a lake, hide its last N years of data, run the forecast, and compare the decoded predictions against the actual recorded spectral values.
- Measure forecast accuracy (e.g. MAE, RMSE) per spectral index and per horizon distance.
- Use this to tune the number of analogs, the forecast horizon, and the similarity method.

### Step 7 — Performance Optimisation (Optional but Recommended)

- The current similarity search fetches all lake embeddings to Python and compares them with a brute-force sliding window. As the number of lakes grows this will become slow.
- Migrate the similarity search to use pgvector's native ANN operators directly in SQL for orders-of-magnitude faster retrieval.

---

## Summary

| Stage | Status |
|-------|--------|
| Satellite image ingestion | ✅ Done |
| Prithvi embedding generation | ✅ Done |
| Embedding storage (pgvector) | ✅ Done |
| Similarity / analog search | ✅ Done |
| Analog-based embedding forecasting | ✅ Done |
| Decoder (embedding → NDVI/NDWI/NBR) | ⬜ Not started |
| Spectral trend derivation | ⬜ Not started |
| Frontend spectral forecast display | ⬜ Not started |
| Backtesting & evaluation | ⬜ Not started |
| pgvector ANN optimisation | ⬜ Not started |
