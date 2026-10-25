# Lake embedding generation (lake + shore tokens)

One embedding per lake and year, stored on `regions`:

| Column | Meaning |
|---|---|
| `lake_embedding` | Prithvi tokens over the lake polygon, pooled |
| `shore_embedding` | Prithvi tokens over the 500 m ring outside the polygon, pooled |
| `embedding` | `normalize(w · lake + (1 − w) · shore)` — the single vector used by similarity and forecasting |
| `lake_weight` | `w` used for `embedding` (default `EMBEDDING_LAKE_WEIGHT` = 0.7) |
| `lake_token_weight`, `shore_token_weight` | Σ of valid-pixel token fractions pooled into each part |
| `tokens_encoded` | tokens fed to Prithvi |
| `embedding_version` | 1 = legacy 1 km cells (10 m, B2–B7); 2 = this method |

## Flow per lake-year

1. Read the merged 30 m GeoTIFF (`S2_BANDS_DOWNLOAD` stack, EPSG:4326, fixed global grid).
2. Rasterise the lake polygon and the 500 m shore ring on the image grid (pixel centres).
3. Tile their joint extent into 224 × 224 px windows (6.72 km). Each window is a
   14 × 14 grid of 16 px tokens (480 m).
4. Per token: fraction of pixels that are valid lake, valid shore, valid.
5. Prithvi input = B2, B3, B4, B8A, B11, B12 (HLS Blue, Green, Red, Narrow NIR,
   SWIR1, SWIR2), nodata filled with the band mean, normalised with the model's
   mean / std.
6. The encoder sees **only tokens touching the lake or shore** (as in MAE
   pre-training, where it saw a 25 % token subset) — distant land never enters
   attention.
7. `lake = Σ lake_frac · v / Σ lake_frac`, `shore = Σ shore_frac · v / Σ shore_frac`,
   both L2-normalised; `embedding = blend(lake, shore, w)`.

A lake-year fails (row stored with `status = 'failed'` and NULL vectors) if it has
fewer than `EMBEDDING_MIN_LAKE_PIXELS` valid lake pixels.

## Re-blending without re-running Prithvi

`POST /embeddings/merge` with `lake_weight` recomputes `embedding` from the stored
parts for the selected years — seconds, no GPU, no imagery.

## Why these choices

- **30 m**: Prithvi was pre-trained on HLS L30 (30 m); tokens are then 480 m.
- **500 m ring**: JRC Global Surface Water over all 829 lakes shows the lake's own
  water-level fluctuation zone ends at ~500 m outside the HydroLAKES polygon
  (0–250 m: 41 % ever-water; 250–500 m: 10 %; beyond: 2–5 % background). It is
  also one token wide, the smallest resolvable ring.
- **Separate pooling**: a joint lake+ring pool would make the land share depend
  on lake size and shape (82 % land for small lakes, 59 % for large at 1 km).
  Pooling separately and blending with a fixed `w` gives every lake the same
  water / shore balance.
