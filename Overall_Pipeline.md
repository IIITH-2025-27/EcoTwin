# EcoTwin — Pipeline Documentation

## What is EcoTwin?

EcoTwin is an AI-powered system for finding analog ecosystems and forecasting their future.
It uses embeddings from Prithvi, a geospatial foundation model, to find lakes whose recent history looks most like a given lake ("twins" / "analogs"). It then uses what actually happened to those twins next to forecast where the given lake is heading.

Coverage: **829 active lakes in India** (HydroLAKES, ≥ 2 km²), **2016–2025**.

> The detailed old-vs-new comparison (bands, resolution, formulas and schema) is in
> [`documents/version2.md`](documents/version2.md). This page gives the overview.

---

## Pipeline at a glance

```text
HydroLAKES ──► 1. Fetch images (GEE) ──► 2. Merge tiles ──┬─► 3. Lake features  ──► lake_features
                 (per lake-year,                          │     (lake pixels only)
                  25 km tiles, 30 m)                      └─► 4. Embeddings     ──► regions
                                                                (lake + 500 m shore,     │
                                                                 Prithvi)                ▼
                                                      5. Merge embeddings (re-blend lake / shore weight)
                                                                                         │
                                       6. Similarity search (twin lakes) ◄───────────────┘
                                                          │
                                       7. Forecast (ecological indices from twins' real history)
                                                          │
                                       8. API + frontend + PDF report
```

Every step can be started from the frontend pipeline menu, and every step **skips
work that is already done and current**, so re-running any of them is safe.

---

## What Has Been Implemented

### Stage 1 — Satellite Image Acquisition (`app/image_acquisition/`)

- **One image per lake-year with every band needed**, used for both features and embeddings:
  Sentinel-2 L2A (`COPERNICUS/S2_SR_HARMONIZED`), yearly **median** composite at **30 m**
  (Prithvi's training resolution).
- **12-band stack** (uint16, reflectance × 10000, nodata 65535):
  B1, B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12 plus **CLEAR_COUNT** (cloud-free scenes per pixel).
- **Cloud masking:** Cloud Score+ (`cs_cdf ≥ 0.6`), plus SCL classes 1 (saturated) and 11 (snow).
- **Area per lake:** the lake polygon buffered by **3.5 km**, split into **25 km tiles**
  (under GEE's download size limit). Every tile sits on a **fixed global 30 m grid**,
  so pixels line up across tiles and years.
- **Reliability:**
  - Transient errors (HTTP 503, timeouts) are retried 3 times with backoff.
  - When GEE answers *"User memory limit exceeded"*, the tile is downloaded in 4 parts
    (up to 16) and stitched back together locally.
  - **Multiple GEE service accounts:** every working key in `app/secrets/gee_key*.json`
    is used. On a quota or rate-limit error (HTTP 429) the downloader switches to the next account.
- **Storage location per year:** each year goes to `SENTINEL_DATA_DIR`
  (`backend/data/sentinel/<year>/`) unless another folder is chosen in the Fetch Images dialog.
  `lake_tiles.image_path` and `lake_images.file_path` record where every file actually is.
- **Progress** is counted per lake-year (the bar ends at 100 %), with tile counts and
  per-lake-year errors. Runs can be cancelled ("cancelling" → "cancelled") and picked up
  again when the dialog is reopened.

### Stage 2 — Merge Tiles (`merge_pipeline.py`, `merger.py`)

- Merges a lake-year's tiles into `<root>/<year>/lake_<id>.tif`, next to the tiles.
- A lake-year is merged only when **all** of its tiles are downloaded, so no images with holes.
- Fixes the tiles' nodata header first. GEE tags downloads `nodata=0`, which would otherwise
  drop pixels whose reflectance really is 0 (dark water).
- Optional **delete tiles** after merging. Merged images are about 3.4 GB per year.

### Stage 3 — Lake Features (`app/services/lake_feature_generator.py`, `app/processing/`)

- Clipped to the **lake polygon only** (no shore). Pixel and cloud statistics count lake pixels only.
- Statistics for **all 11 spectral bands** (mean, std, min, max, median) plus clear-observation statistics.
- **14 spectral indices** on true reflectance, with correct NIR and SWIR bands:
  NDVI, NDWI, EVI, SAVI, MSAVI, GCI, NDRE, MNDWI, NDMI, AWEI, BSI, NDBI, NBR, NBR2.
- GLCM texture on B8, and water statistics.
- `feature_version = 2`. Rows from the old method, or rows computed before their image was
  merged again, are recomputed automatically.

### Stage 4 — Embedding Generation (`app/embedding_pipeline/`)

- **Pre-trained Prithvi-EO-1.0-100M, no fine-tuning.** Input bands are the HLS set
  B2, B3, B4, B8A, B11 and B12 at 30 m.
- The lake and a **500 m shore ring** are covered by 224 × 224 px windows, split into
  480 m tokens. **Only tokens that touch the lake or the shore are encoded.**
- Token embeddings are pooled into two vectors per lake-year, weighted by the share of
  valid (cloud-free) lake or shore pixels in each token:
  - `lake_embedding` (768-d)
  - `shore_embedding` (768-d)
- The **combined embedding** used for similarity and forecasting is
  `normalize(w · lake + (1 − w) · shore)`, with **w = 0.7** (`EMBEDDING_LAKE_WEIGHT`).
- Stored on `regions` (`embedding_version = 2`), with token weights and the weight used.
- An embedding is redone when its image is merged again later.
  If no valid shore exists, the combined vector is the lake vector alone.
- Runs on CPU in about 0.2–4 s per lake-year.

### Stage 5 — Merge Embeddings (Re-blend)

- Recomputes the combined `embedding` from the stored lake and shore parts with a **chosen
  lake weight** (slider and presets in the frontend). No Prithvi inference is needed, and it
  takes seconds.
- New embeddings are always created with the weight already in use, so every lake-year stays comparable.

### Stage 6 — Similarity Search (`app/services/similarity_service.py`)

- Given a lake and an anchor year, the query is a **5-year trajectory** of its embeddings.
- Every 5-year sliding window of every other lake is compared with it
  (cosine, Euclidean or KNN inner product), and the best window per lake is kept.
- Candidates are ranked, and the top-K twins are returned together with their `matched_year`.

### Stage 7 — Forecasting

There are two forecast paths:

| | Ecological index forecast (**live**) | Embedding forecast (older) |
|---|---|---|
| Service | `EcologicalForecastService` | `ForecastService` |
| Endpoint | `GET /api/v1/forecast/ecological/{region_id}` | forecast endpoint (embedding horizons) |
| How it works | Twins found by embedding similarity; for each twin, the **real** change in 5 indices from `lake_features` over +1, +2 and +3 years; combined with rank weights | Weighted average of the twins' future embeddings |
| Output | Direction, weighted score and **expected value** per index and year | Forecast embedding vectors; NDVI, NDWI and NBR are still **`0.0` placeholders** (no decoder) |
| Used by | Forecast panel, PDF report | Not used for display |

The live forecast uses NDCI, NDVI, NDWI, turbidity ratio and red-edge slope
(see [`backend/app/services/README_ECOLOGICAL_FORECAST.md`](backend/app/services/README_ECOLOGICAL_FORECAST.md)).

### Stage 8 — API, Frontend & Report

- FastAPI backend, React frontend (map, analog panel, forecast panel, temporal charts), and a PDF report.
- Pipeline dialogs: Sync Lakes, Fetch Images, Merge Image Tiles, Generate Embeddings,
  Merge Embeddings, Generate Lake Features. Each is gated by `pipeline_permissions`.
  The separate **Fetch B8** step was removed, because B8 is now part of the main stack.
- Results are cached in Redis.

---

## Database (PostgreSQL 14 + PostGIS + pgvector)

| Table | Content |
|---|---|
| `lakes` | HydroLAKES polygons (11,130 in India, 829 active) |
| `lake_tiles` | Download tiles per lake-year (bbox, status, file path) |
| `lake_images` | One row per lake-year: `completed` (tiles), `merged` (merged GeoTIFF), `failed` |
| `lake_features` | Per lake-year features (`feature_version`) |
| `regions` | Per lake-year `embedding`, `lake_embedding`, `shore_embedding`, weights (`embedding_version`) |
| `pipeline_permissions`, `reports`, `india_states` | App tables |

Migrations: Alembic, currently at **024**.
- 021: all-band feature columns.
- 022: lake and shore embeddings.
- 023: dropped `sub_regions`; the old 1 km cell embeddings are gone.
- 024: dropped the `fetch_b8` permission.

Check the data with `backend/scripts/postgres/USEFULL_Verify_results.sql`
(`SELECT * FROM verify_counts(ARRAY[2016,…,2025])`).

---

## Current Data (local DB, v2 method — complete)

| Year | Merged images | Embeddings | Features |
|---|---|---|---|
| 2016 | 816 | 816 | 816 |
| 2017 | 820 | 820 | 820 |
| 2018–2025 | 829 each | 829 each | 829 each |
| **Total** | **8,268** | **8,268** | **8,268** |

- **Images:** 30 m, 12 bands, about 33 GB in total, on `/media/vikash/Entertainment/ecotwin_sentinel/<year>/`.
- **Gaps:**
  - 19 lake-years have no Sentinel-2 L2A scenes in GEE: coastal Tamil Nadu and Puducherry
    in 2016 (11) and 2017 (8).
  - 3 lake-years with no cloud-free lake pixels were removed.
- **Backup:** `v6_ecotwin_till_all_bands.dump` (pg_dump 14, about 114 MB; restore steps in `README_restore.md`).
  It contains every table, but not the GeoTIFFs.
- **Run time:** about 1 hour per year for one download at a time. With 3 years in parallel
  (one GEE account each), all ten years took about 12 hours of wall-clock time, including recoveries.
- **Batch runs:** `backend/scripts/run_year_pipeline.py` downloads year after year and processes
  each finished year (merge → embeddings → features) in a **separate process**. Inside one
  long-lived server process, memory built up to about 4 GB and the server was OOM-killed on an 8 GB machine.

---

## Known Limitations

- **Embedding-level forecast:** the decoder (embedding → NDVI / NDWI / NBR) is not built,
  so that endpoint still returns `0.0` placeholders and `"stable"` trends.
- **Similarity scores are compressed:** raw Prithvi cosine similarities cluster around 0.97
  (one shared direction carries 47 % of the variance). The ranking works, but the scores
  separate poorly. Subtracting the mean embedding spreads them to roughly −0.6 to +0.7 and
  slightly improves the neighbours.
- **Lake names:** only 37 of the 829 active lakes are named in HydroLAKES.
- **Lake weight 0.7** comes from literature and reasoning; it has not been calibrated on our data yet.

---

## What Needs to Be Done Next

### 1. Similarity improvements
- Subtract the dataset mean embedding (mean-centring) before cosine similarity.
- Restrict search to `embedding_version = 2`, so legacy rows are never compared.
- Optional: use pgvector ANN in SQL instead of brute-force windows in Python.

### 2. Embedding quality and weight calibration
- **Probe test:** predict NDWI, NDCI, turbidity and water fraction from the embeddings with
  a cross-validated linear model, to show the embeddings carry the water-quality signal.
- **Stability test:** a lake's own embedding in another year should be its nearest match.
- Run both tests for lake weights 0.5–1.0 (re-blend only), then apply the best weight with Merge Embeddings.

### 3. Forecast validation (backtesting)
- Hide a lake's last N years, forecast them, and compare against the real `lake_features`
  (MAE / RMSE per index and horizon).
- Use the results to tune the number of twins, the rank weights and the similarity method.

### 4. Decoder for the embedding forecast (optional)
- Either train a small model mapping embedding → indices on the 8,268 paired lake-years,
  or retire the embedding forecast endpoint in favour of the ecological forecast.

### 5. Lake names
- Fill names from **GRanD** (`Grand_id` link, about 243 reservoirs), then **OpenStreetMap**
  water polygons, then **India-WRIS**. Fall back to "Lake near *village*, *district*".
  Record the source in a `name_source` column.

### 6. Housekeeping
- Save merge errors in `lake_images.error_message`.
- Use a unique probe file name in `storage.py`, so parallel downloads don't collide.
- Remove the revoked `gee_key.json` from git.
- Migrate Supabase to Alembic 024 when the hosted app should use the v2 data.
- Update the project report with the v2 method.

---

## Summary

| Stage | Status |
|-------|--------|
| Satellite image acquisition (12-band, 30 m, Cloud Score+) | ✅ Done (v2) |
| Tile merge (nodata-safe, tile cleanup) | ✅ Done |
| Lake features (all bands, 14 indices, lake pixels only) | ✅ Done (v2) |
| Prithvi lake + shore embeddings | ✅ Done (v2) |
| Re-blend lake / shore weight | ✅ Done |
| Data for 2016–2025 (8,268 lake-years) | ✅ Done |
| Similarity / analog search | ✅ Done (mean-centring pending) |
| Ecological index forecast (live) | ✅ Done |
| Embedding forecast decoder | ⬜ Not started |
| Embedding quality and weight calibration | 🟡 Basic checks done |
| Backtesting and evaluation | ⬜ Not started |
| Lake names (GRanD / OSM) | ⬜ Not started |
| pgvector ANN optimisation | ⬜ Not started |
