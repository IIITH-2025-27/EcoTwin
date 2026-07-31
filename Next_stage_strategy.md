# EcoTwin — Decoder Integration: Next Steps

## Context: What We Have Right Now

At the end of the forecasting pipeline, the system produces a **forecast embedding** for each future year.
This is a **768-dimensional float vector** — a weighted average of real analog lakes' future Prithvi embeddings.

These forecast embeddings are fully computed but currently discarded after building the forecast response.
The spectral indicator fields (`NDVI`, `NDWI`, `NBR`) in the forecast are set to `0.0` as placeholders.

The goal of this next stage is to convert those forecast embedding vectors into meaningful spectral index values — without training any new model.

---

## Important: Understanding the Stored Embedding Format

Before choosing a decoder strategy, it is critical to understand **what our embeddings actually are**.

Prithvi is a Vision Transformer (ViT) based Masked Autoencoder (MAE).
When it processes a satellite image patch, it produces a sequence of spatial tokens — one token per image patch.

**What we store is NOT the full token sequence.**

Our pipeline (`prithvi_inference.py`) does the following:
1. Runs the Prithvi encoder on the satellite image.
2. Takes all spatial patch tokens (skipping the CLS token).
3. **Mean-pools** them into a single 768-dimensional vector.
4. **L2-normalises** that vector.
5. Stores this single normalised vector in the database.

This means our stored embedding is a compressed, pooled summary of the full encoder output — not the raw token sequence that Prithvi's MAE decoder expects as input.

---

## Why Prithvi's MAE Decoder Cannot Be Used Directly

Prithvi's built-in MAE decoder expects the **full unmasked token sequence** from the encoder (typically hundreds of tokens), not a single pooled 768-dim vector.

Our forecast embedding is:
- A mean-pooled and L2-normalised summary vector
- A weighted average across multiple analog lakes' pooled vectors
- A single 768-dim vector, not a token sequence

Feeding this directly into Prithvi's MAE decoder would not produce meaningful results because the decoder's input space (a sequence of tokens with positional embeddings) does not match our single pooled vector.

---

## Recommended Approach: Spectral Value Weighted Averaging (No Decoder Needed)

The cleanest solution avoids the decoder problem entirely.

Instead of decoding the forecast embedding vector back into spectral bands, we leverage the fact that we already know **which analog lakes** were used and **exactly which future years** their data came from.

### Core Idea

The forecast embedding for horizon year `H` is a weighted average of the future embeddings of the selected analog lakes. We can apply **the exact same weights** to the analog lakes' actual spectral index values for that same year — and get a valid forecast for NDVI, NDWI, and NBR without any decoding at all.

### Step-by-Step

**Step 1 — Store Spectral Indices Alongside Embeddings**

For every lake-year entry in the database, compute and store the NDVI, NDWI, and NBR values derived from the raw satellite bands. These are pure mathematical formulas applied to the raw Sentinel-2 band data that already flows through the pipeline:

- `NDVI = (NIR − Red) / (NIR + Red)` — vegetation health
- `NDWI = (Green − NIR) / (Green + NIR)` — surface water extent
- `NBR  = (NIR − SWIR2) / (NIR + SWIR2)` — burn severity

This can be computed during the existing image ingestion phase, before or alongside the Prithvi embedding step. No new model is needed — these are band arithmetic formulas.

**Step 2 — Pass Analog Spectral Values Through the Forecasting Module**

The `ForecastingModule` currently fetches the embedding timeline for each analog lake.
Extend this to also fetch the spectral index values (NDVI, NDWI, NBR) for each year of each analog lake.

**Step 3 — Apply the Same Weights**

For each forecast horizon year (offset 1, 2, 3, …):
- Look up the NDVI, NDWI, NBR of each valid analog lake at `matched_window_end + offset`.
- Apply the same similarity-derived weights already computed for the embedding forecast.
- Compute the weighted average of NDVI values → forecast NDVI for that year.
- Repeat for NDWI and NBR.

**Step 4 — Populate the ForecastHorizon Fields**

Replace the `0.0` placeholders in `ForecastHorizon` with these computed weighted-average spectral values.

---

## Why This Approach Is Sound

| Property | Explanation |
|----------|-------------|
| No training required | Pure arithmetic — no model, no weights, no GPU |
| No decoder required | We use actual ground-truth spectral values from the analog lakes |
| Consistent with the embedding forecast | Uses identical analog selection and identical weights |
| Interpretable | Forecast is literally "the weighted spectral future of your closest historical matches" |
| Accurate | Ground-truth spectral values from real future years, not approximations |
| Easy to implement | The analog lake IDs, future years, and weights are all already available in `EmbeddingForecastResult` |

---

## Alternative: Linear Probe (Fallback if Spectral Data is Unavailable)

If for any reason the raw band data is not accessible and spectral indices cannot be computed from the original imagery, a very lightweight alternative exists.

A **linear probe** is a single linear layer (or simple ridge regression) that maps a 768-dim embedding vector to an NDVI/NDWI/NBR scalar. This is the simplest possible "trained" decoder and can work with very few examples (even tens of data points) because it has very few parameters.

The training data for this would come from existing lake-year pairs where we already have both the stored embedding and the known spectral index value. Since we have historical data for all analog lakes, this data is already available in the system.

This is mentioned only as a fallback — the spectral weighted averaging approach above is preferred.

---

## What Needs to Change in the Codebase

### Database

- Add `ndvi`, `ndwi`, `nbr` columns to the `regions` table (or a separate `region_spectral` table).
- Populate these during the image ingestion / sync pipeline using band arithmetic on the raw Sentinel-2 data.

### Embedding Repository

- Add a query method to fetch `(year, ndvi, ndwi, nbr)` for a given `lake_id`, similar to the existing `get_timeline_for_lake`.

### Forecasting Module

- Extend the embedding lookup to also retrieve spectral values alongside embeddings.
- After computing analog weights, apply those same weights to spectral values at each horizon offset.
- Return forecast NDVI, NDWI, NBR per year alongside the existing forecast embeddings.

### Forecast Service

- Pass the decoded spectral values into the `ForecastHorizon` objects (replacing the `0.0` placeholders).
- Use the spectral trend across forecast years to derive `vegetation_trend`, `water_trend`, `burn_severity_trend` labels (e.g., compare mean of horizon years vs current year).

### Frontend

- Display NDVI, NDWI, NBR as time-series charts across the forecast horizon years.
- Show trend labels as colour-coded badges (improving / stable / degrading).

---

## Summary

| Question | Answer |
|----------|--------|
| Do we need to train a decoder? | No |
| Can we use Prithvi's MAE decoder directly? | No — our embeddings are pooled vectors, not raw token sequences |
| What is the recommended approach? | Weighted average of analog lakes' actual spectral index values |
| What data do we need? | NDVI/NDWI/NBR computed from existing raw Sentinel-2 bands already in the pipeline |
| Is this a large change? | No — the analog selection, weights, and future years are already produced by the current system |
