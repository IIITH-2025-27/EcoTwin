# Ecological Index Forecast

This document describes the forecast that is actually live end-to-end today:
the twin-lake, weighted-delta ecological index forecast served by
`EcologicalForecastService`, rendered in the Forecast panel, and embedded in
the PDF report. It is a different, older pipeline from the one described in
`README_FORECAST_EMBEDDINGS.md` (embedding-vector analog forecasting with an
unwired decoder, whose REST endpoint still returns `0.0` placeholders). This
one has no decoder step — it forecasts *direction and expected value*
directly from real historical Sentinel-2 band means, not from decoded
embeddings.

## Current API status

`GET /api/v1/forecast/ecological/{region_id}` is fully wired: it queries real
`lake_features` band data, finds twin lakes via embedding similarity, and
returns a 3-year forecast per ecological index — direction, weighted score,
**expected value**, and the raw per-twin deltas behind that score. This is
the response `useEcologicalForecast` (frontend) and `build_report_context`
(PDF report) both consume.

## What problem this solves

Target lake A has real satellite history up to some `anchor_year`. There is
no real data for A beyond that. Rather than training a per-lake time-series
model, EcoTwin finds other lakes ("twins") whose Prithvi embedding
trajectory closely resembles A's recent trajectory, and uses *those twins'
own already-observed year-over-year change* as a stand-in for what A is
likely to do next. This is analog forecasting, not extrapolation from A's
own history.

## Pipeline overview

```text
target lake's latest lake_features row
    -> compute 5 ecological indices (anchor_indices)
    -> embedding similarity search -> ranked twin lakes, each with its own matched_year
    -> for each twin, for h = 1..3: delta = index(matched_year + h) - index(matched_year)
    -> weighted_score(index, h) = sum(rank_weight * delta) over twins with data at h
    -> expected_value(index, h) = anchor_indices[index] + weighted_score(index, h)
    -> direction(index, h) = classify(weighted_score, twins_contributing)
```

Implementation: `app/services/ecological_forecast_service.py`,
`EcologicalForecastService.generate_ecological_forecast`.

## 1. The five indices

Computed on-the-fly from `lake_features` band means (B2–B7 only — no B8/NIR,
no SWIR, no thermal band is available in the merged imagery). Implementation:
`app/services/index_calculator.py::compute_ecological_indices`.

| Key | Formula | What it tracks |
| --- | --- | --- |
| `ndci` | `(B5 − B4) / (B5 + B4)` | Chlorophyll-a / algal bloom |
| `ndvi_b7` | `(B7 − B4) / (B7 + B4)` | Vegetation vigor / greenness proxy |
| `ndwi` | `(B3 − B7) / (B3 + B7)` | Water mask / wetness (note: this is a *different* NDWI formula than the McFeeters `(Green−NIR)/(Green+NIR)` used elsewhere in `app/processing/spectral_indices.py` — this service is restricted to B2–B7 and has no true NIR band) |
| `turbidity_ratio` | `(B4 − B3) / (B4 + B3)` | Water clarity / suspended sediment |
| `red_edge_slope` | `(B7 − B5) / 78` (Δλ between 705 nm and 783 nm) | Pigment concentration trend, units: reflectance per nm |

If any of B2–B7 is missing/non-finite for a given lake-year, all five indices
are `None` for that row (`_is_missing` guard). Divisions near zero return
`0.0` rather than raising (`_safe_ratio`, epsilon `1e-10`).

## 2. Finding twin lakes

Implementation: `app/services/similarity_service.py::SimilarityService.search_analogs`,
called with `top_k = min(num_analogs * 4, 50)` so there's headroom to skip
candidates that lack usable band data.

1. **Query trajectory**: the target's last 5 years of embeddings ending at
   `anchor_year` (`_select_query_trajectory`, `window_size=5`).
2. **Candidate windows**: for every other lake, every possible 5-year sliding
   window over its own embedding history (`_build_candidate_windows`).
3. **Best window per candidate**: mean pairwise similarity (cosine, euclidean,
   or knn — `_compute_pair_similarity`) between the query's 5 years and the
   candidate's window, for every window; keep the candidate's best-scoring
   window (`_compute_window_similarity`).
4. **`matched_year`** = the *last* year of that best window — this is the
   year in the twin's own history whose recent trajectory looked most like
   A's.
5. Cosine/KNN scores are rescaled from `[0.5, 1.0] -> [0.0, 1.0]`
   (`_rescale_score`, `_COSINE_FLOOR = 0.5`) because Prithvi embeddings are
   L2-normalized and raw cosine scores cluster tightly near 1.0.
6. Candidates are sorted by similarity score; the ecological forecast service
   then walks that ranked list and keeps the first `num_analogs` (default 5)
   that actually have usable `lake_features` band data — **`rank` is this
   filtered list position, not a stored/similarity-derived field**
   (`ecological_forecast_service.py`, `rank = len(twin_data) + 1`).

## 3. Per-twin deltas — offset from the twin's own base, not chained

For each kept twin, for each horizon `h = 1, 2, 3`:

```text
future_yr = twin_matched_year + h
delta[index][h] = index_value(future_yr) - index_value(twin_matched_year)
```

Both `index_value(...)` calls are computed from that twin's own real
`lake_features` rows (`_fetch_band_rows`, `_compute_indices_from_row`) — not
synthetic, not interpolated. Twins missing a row for `matched_year + h`
simply contribute no delta for that `h` (their weight becomes 0 for that
year only — not redistributed to other twins).

**Why cumulative-from-base and not chained/compounding.** `delta[h]` is
always measured against the twin's *fixed* `matched_year`, never against
`matched_year + h - 1`. This means every horizon's delta is one real
subtraction between two real satellite observations — h=1, h=2, and h=3 are
independently anchored to ground truth, so none of them compounds another
horizon's estimation error. A chained design (forecast h=2 by adding an
increment onto a *forecasted* h=1 value) would stack synthetic error across
horizons; this design never produces an intermediate synthetic value to
chain from.

## 4. Weighted score, expected value, and classification

Fixed rank weights (not derived from the similarity score itself):

| Rank | Weight |
| --- | --- |
| 1 | 0.28 |
| 2 | 0.24 |
| 3 | 0.20 |
| 4 | 0.16 |
| 5 | 0.12 |

For each index and each forecast year `anchor_year + h`, weights are first
**renormalized over only the twins that have data for that specific `h`** —
a twin's fixed rank weight only means "28% of the vote" when all 5 twins are
present; if some are missing, their weight is not simply dropped from the
sum (which would silently shrink the score toward "stable" regardless of the
actual signal), it is redistributed proportionally among whoever remains:

```text
total_weight     = sum(fixed_weight_i)              over twins i with data at h
normalized_w_i   = fixed_weight_i / total_weight     (0.0 if total_weight == 0)
weighted_score   = sum(normalized_w_i * delta_i[h])  over twins i with data at h
expected_value   = anchor_indices[index] + weighted_score
```

Example: if only rank 1 (0.28) and rank 3 (0.20) have data for a given year,
`total_weight = 0.48`, so their renormalized weights become `0.28/0.48 ≈
0.583` and `0.20/0.48 ≈ 0.417` — still summing to 1.0, preserving their
*relative* influence without being diluted by the two absent twins. This
keeps `weighted_score` a true weighted average (bounded by the min/max of
the contributing deltas) regardless of how many twins dropped out for that
year, so the fixed classification threshold below means the same thing every
year. `TwinDeltaContribution` carries both `fixed_weight` (the twin's
constant rank weight) and `normalized_weight` (this year's renormalized
weight) so the audit trail and UI can show when a twin's effective influence
differs from its nominal rank weight.

`expected_value` is always anchored to the target lake's own real
`current_value` — it is *not* built by chaining `expected_value(h-1)` plus a
further increment. Each year's expected value is one independent addition of
that year's own weighted score onto the same fixed anchor.

Classification (`_classify`):

```text
twins_contributing < 2          -> "uncertain"
weighted_score >  +0.005        -> "up"
weighted_score <  -0.005        -> "down"
otherwise                       -> "stable"
```

`_DIRECTION_THRESHOLD = 0.005`, `_MIN_TWINS_FOR_DIRECTION = 2`,
`_FORECAST_HORIZON = 3` (hardcoded).

## 5. Response contract

`app/schemas/forecast.py::EcologicalForecastResponse`:

```python
EcologicalForecastResponse(
    region_id=...,
    lake_id=...,
    current_year=2025,               # anchor_year
    forecast_years=[2026, 2027, 2028],
    index_forecasts=[
        IndexForecast(
            index_name="ndci",
            current_value=0.0421,     # anchor_indices["ndci"]
            yearly_directions=[
                YearlyDirection(
                    year=2026,
                    direction="up",
                    weighted_score=0.0138,
                    twins_contributing=4,
                    expected_value=0.0559,        # current_value + weighted_score
                    twin_deltas=[
                        TwinDeltaContribution(
                            lake_id=142, rank=1, matched_year=2020,
                            delta=0.031, fixed_weight=0.28, normalized_weight=0.318,
                            weighted_contribution=0.00986,
                        ),
                        # ... one entry per twin that had data for this year;
                        # normalized_weight differs from fixed_weight whenever
                        # not all 5 twins contributed this year (see §4).
                    ],
                ),
                # ... 2027, 2028
            ],
        ),
        # ... ndvi_b7, ndwi, turbidity_ratio, red_edge_slope
    ],
    twins_used=[
        TwinContribution(
            lake_id=142, region_id=..., rank=1, fixed_weight=0.28,
            matched_year=2020, similarity_score=0.91, embedding_distance=0.09,
            future_window=[2021, 2022, 2023],
            index_values={"ndci": {"2020": 0.011, "2021": 0.042, ...}, ...},
        ),
        # ...
    ],
    audit_report=ForecastAuditReport(...),   # human-readable trace of every step above
    explanation="...",
)
```

`TwinContribution.index_values` is keyed by the twin's *own real observed
years* (matched_year onward) — it does not align to the target's forecast
calendar years, since a twin matched at 2020 and one matched at 2024 each
contribute from their own distinct historical window. Only the offset `h` is
shared across twins, not the calendar year.

`twin_deltas` (new, per `YearlyDirection`) exists specifically so consumers
don't have to re-derive "which twins fed into this year's score" from
`twins_used` + manual offset math — it's already resolved per forecast year.

## 6. Frontend consumption

`frontend/src/components/ForecastPanel/ForecastPanel.tsx`:

- **Trajectory line chart** (`ecoChartData`): plots `current_value` at the
  anchor year, then `yearly_directions[i].expected_value` for each forecast
  year, directly from the API — no client-side arithmetic.
- **Year cards**: direction arrow + `expected_value` + `weighted_score` +
  `twins_contributing`, per index per forecast year.
- **`TwinDeltaChart`**: a grouped bar chart (twin on the x-axis, one bar per
  forecast year) built by pivoting `yearly_directions[*].twin_deltas` by
  `rank` — shows the raw, unweighted per-twin deltas that were summed into
  each year's `weighted_score`, for whichever index is currently selected.

## 7. PDF report consumption

`app/services/report/context.py` + `app/services/report/templates/sections/forecast.html`:

- `_build_eco_forecast_items` calls the same `EcologicalForecastService` and
  reuses `expected_value` directly (no re-derivation) to build each index's
  chart `points` and per-year `EcoIndexYearChange` table row.
- `_build_twin_delta_rows` performs the same twin-by-rank pivot as the
  frontend's `TwinDeltaChart`, producing `EcoIndexForecastItem.twin_delta_rows`
  (one `TwinDeltaRow` per twin, keyed by year -> `TwinDeltaBar`).
- `forecast.html` renders: (1) a hand-built inline-SVG line chart of the
  trajectory, (2) a per-year expected-value table with direction arrows, (3)
  one small inline-SVG grouped bar chart per index — same twin/year pivot,
  same color palette (`#38bdf8, #a78bfa, #fb7185, #facc15, #34d399`) as the
  frontend chart, so the PDF and the live UI show the same numbers the same
  way. No headless browser or screenshot capture is involved anywhere in the
  report pipeline — every chart is regenerated from the same API response,
  once server-side (for the PDF) and once client-side (for the panel).

## Known limitations

- **3-year horizon is hardcoded** (`_FORECAST_HORIZON = 3`), not configurable
  per request.
- **A twin missing a future offset silently drops out** for that year only.
  Its weight *is* redistributed proportionally among the twins that remain
  (see §4, `normalized_weight`), so `weighted_score` stays a true weighted
  average regardless of how many twins contributed. What is **not**
  compensated for is confidence: 2 twins renormalized to sum to 1.0 produce a
  score on the same scale as 5 twins would, even though it reflects less
  independent evidence — `twins_contributing < 2 → "uncertain"` is the only
  guard against low-evidence years, and it doesn't distinguish "2 twins, both
  top-ranked" from "2 twins, both bottom-ranked."
- **`rank` is list position after filtering, not a similarity-score-derived
  rank field** — two forecasts run seconds apart could reorder ranks if the
  underlying candidate set changes (e.g. new data ingested).
- **No error bars / confidence interval** on `expected_value` — only the
  categorical `direction` plus `twins_contributing` as a rough confidence
  proxy.
- **Different NDWI formula than the rest of the codebase** — see the table
  in §1. Don't compare `ndwi` from this service directly against NDWI values
  from `app/processing/spectral_indices.py` or the ML classifier.

## Primary code locations

- `app/services/ecological_forecast_service.py` — orchestration: anchor,
  twin deltas, weighted score, expected value, classification
- `app/services/index_calculator.py` — the five index formulas
- `app/services/similarity_service.py` — five-year trajectory matching /
  twin selection
- `app/schemas/forecast.py` — `EcologicalForecastResponse` and nested schemas
- `app/services/report/context.py`, `app/services/report/templates/sections/forecast.html`
  — PDF report rendering of the same data
- `frontend/src/components/ForecastPanel/ForecastPanel.tsx` — live UI
  rendering of the same data
- `frontend/src/hooks/useEcologicalForecast.ts`, `frontend/src/api/forecast.ts`
  — frontend fetch layer (`GET /forecast/ecological/{region_id}`)
