# EcoTwin — Version 2 Pipeline Changes

**Scope:** backend data pipeline: image download, merge, lake features, Prithvi embeddings, and the database schema.
**Status:** implemented and tested end-to-end on 3 lake-years. The full re-run (829 lakes × 2016–2025) has not been started yet.
**Why a full re-run is needed:** version 1 fed Prithvi the wrong bands at the wrong scale, and several lake features used substitute bands. None of the v1 embeddings or features can be reused.

---

## 1. Summary of major changes

1. **Prithvi now gets the bands it was trained on.** Prithvi-EO-1.0 was pre-trained on HLS **L30** (Landsat numbering): `B02…B07` there means Blue, Green, Red, Narrow NIR, SWIR1 and SWIR2. Version 1 read those names as Sentinel-2 B2–B7, so three of the six channels it received were red-edge bands the model never saw. Version 2 sends Sentinel-2 **B2, B3, B4, B8A, B11, B12**.
2. **One image per lake-year feeds everything.** A single 12-band image (B1–B8, B8A, B11, B12 plus a cloud-free observation count) is downloaded once. Embeddings and lake features both read from it, so the separate B8 pass is no longer needed.
3. **30m resolution instead of 10m.** Prithvi was trained at 30m. Version 1 stretched 1km cells to 224px (about 4.5m per pixel), roughly 7× off the model's scale. At 30m the image feeds Prithvi directly, and Earth Engine computes about 9× fewer pixels.
4. **Spectral indices use real NIR and SWIR on true reflectance.** Version 1 used B5 as a stand-in for NIR and B7 for SWIR, so MNDWI, NDMI, NBR, BSI, NDBI and AWEI were not the real indices. EVI, SAVI and MSAVI were also computed on values scaled ×10000 instead of 0–1 reflectance, which made them wrong.
5. **New embedding method: lake + 500m shore.** Prithvi now encodes only the 480m tokens that touch the lake polygon or a 500m ring around it. A lake vector and a shore vector are pooled separately, then blended (0.7 / 0.3) into the single embedding used by similarity and forecasting. Both parts are stored, so the weight can be changed later without re-running the model.
6. **Composites are cleaner.** Clouds are masked with Cloud Score+ instead of the SCL band alone. Every tile and every year sits on one fixed 30m pixel grid. Nodata is 65535 instead of 0.
7. **Re-runs are safe.** Each stage now skips finished work and refuses stale or incomplete inputs, so an interrupted run can resume without mixing old and new data.

---

## 2. Bands

| Item | Version 1 | Version 2 | Reason |
|---|---|---|---|
| Downloaded bands | B2, B3, B4, B5, B6, B7 | **B1, B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12 + CLEAR_COUNT** | One image must serve Prithvi, the water-quality forecast (B5, B7, B8) and the SWIR indices (B11, B12). B1 was added for water-quality work. CLEAR_COUNT records how many cloud-free scenes each pixel's median used. |
| Prithvi input | B2, B3, B4, **B5, B6, B7** | B2, B3, B4, **B8A, B11, B12** | Confirmed three ways: the model card ("HLS L30 … Narrow NIR, SWIR1, SWIR2"), the example files `HLS.L30…B02…B07.tif`, and their pixel values (channel 5 > channel 6, the SWIR1 > SWIR2 pattern; red-edge bands would rise steadily instead). |
| B8 (NIR) | separate Earth Engine pass (`reduceRegions`) | part of the main image | Same pixels and cloud mask as every other band; one pass fewer. |
| Data type | float64 | **uint16** (rounded) | Sentinel-2 SR is integer reflectance ×10000, so nothing is lost and files are 4× smaller. |

## 3. Download and composite

| Item | Version 1 | Version 2 | Reason |
|---|---|---|---|
| Resolution | 10m | **30m** | Matches Prithvi's training scale; ~9× less Earth Engine work. |
| Cloud mask | SCL classes 3, 7–11 | **Cloud Score+** `cs_cdf ≥ 0.6`, plus SCL 1 (saturated) and 11 (snow/ice) | Cloud Score+ is Google's current recommended Sentinel-2 mask and catches haze and shadow that SCL misses. Verified available for 2016+. |
| Composite | yearly median | yearly median (unchanged) | — |
| 2016–2017 data | report says "Level-1C fallback" | surface reflectance for all years | Earth Engine has real L2A data for 2016 (ESA baseline 05.00), confirmed by direct query. No fallback exists in the code; the report statement is inaccurate. |
| Buffer around lake | 1.2km | **3.5km** | Gives Prithvi's 6.72km window full context. Cheap at 30m. |
| Area computed | bounding box of the buffered lake | **the buffered lake shape** (simplified to 30m) | Across all lakes the shape covers 64% of its bounding box, so ~36% of the median work is skipped. |
| Tile size | 8.5km squares, always full size | **25km, trimmed** to the buffered lake | At most 20.4MB per request across India (limit 32MB); a small lake downloads 349×296 px instead of a full tile (empty pixels: 85.7% → 22%). |
| Pixel grid | each tile on its own grid | **one fixed global 30m grid** | Tiles merge without resampling, and a lake's pixels line up exactly across years. Tested: offset 0.0000 px between 2016 and 2023. |
| Nodata value | 0 (Earth Engine default, untagged) | **65535**, written into the file | 0 is a real value (very dark water in SWIR; CLEAR_COUNT = 0). 65535 never occurs in real data. |
| Tile merge | nodata not passed to the merge | nodata passed explicitly | Otherwise one tile's fill could overwrite a neighbour's valid pixels where they overlap. |

## 4. Spectral indices (`lake_features`)

All indices are computed on **true reflectance** (stored value ÷ 10000).

| Index | Version 1 | Version 2 | Reason |
|---|---|---|---|
| NDVI, GCI, NDWI | B5 as NIR | **B8** | B5 (705nm) is red edge, not NIR. |
| EVI | B5; ×10000 values | `2.5(B8−B4)/(B8+6B4−7.5B2+1)` on reflectance | The `+1` constant assumes 0–1 reflectance. |
| SAVI, MSAVI | B5; ×10000 values | B8 on reflectance | On ×10000 values SAVI reduced to roughly NDVI×1.5. |
| NDRE | (B5−B6)/(B5+B6) | **(B8A−B5)/(B8A+B5)** | Standard Sentinel-2 definition. |
| MNDWI | (B3−B7)/(B3+B7) | **(B3−B11)/(B3+B11)** | B7 (783nm) is near-infrared, so the old MNDWI was really another NDWI. |
| NDMI, BSI, NDBI | B7 as SWIR | **B11** | Real SWIR1. |
| NBR | (B5−B7)/(B5+B7) | **(B8−B12)/(B8+B12)** | Real NIR and SWIR2. |
| NBR2 | (B6−B7)/(B6+B7) | **(B11−B12)/(B11+B12)** | Standard definition. |
| AWEI | one stand-in band for both SWIR terms | **4(B3−B11) − (0.25·B8 + 2.75·B12)** | AWEInsh uses SWIR1 and SWIR2 separately; needs reflectance. |
| GLCM texture band | B5 | **B8** | NIR, as intended. |
| Visible brightness | first three bands | B2, B3, B4 by name | Adding B1 shifted band positions; all positions are now looked up by name. |

The forecast indices (NDCI, NDVI, NDWI, Turbidity, Red Edge Slope) were already correct and are unchanged.

Effect on Rihand (2024): MNDWI went from 0.246 to **0.501**, and NDVI from 0.003 to **−0.144**. Water now reads as water.

## 5. Lake feature statistics

| Item | Version 1 | Version 2 | Reason |
|---|---|---|---|
| Band statistics | B2–B7 (+ B8 from the separate pass) | **all 11 spectral bands**: mean, std, min, max, median | The full image is available. |
| Composite quality | none | `clear_obs_mean / min / median` | Flags unreliable composites (2016–17 have fewer scenes). |
| Pixel statistics (`pixel_count`, `coverage_percent`, `cloud_percent` …) | counted over the **rectangle around the lake** | counted over **lake pixels only** | Everything outside the shoreline was counted as cloud: Rihand showed 69% "cloud" when no lake pixel was masked. This explains why v1 coverage stayed at ~35% in every year. |
| Pixels used by band, index and water statistics | lake polygon only | lake polygon only (unchanged) | Verified: 0 valid pixels outside the polygon. |
| Version marker | — | `feature_version = 2` | The generator recomputes any row from an older method instead of skipping it. |

## 6. Embeddings

| Item | Version 1 | Version 2 | Reason |
|---|---|---|---|
| Unit embedded | 1km × 1km cells | **480m Prithvi tokens** | Follows the shoreline more closely; no grid-alignment artefacts. |
| Which area | cells with ≥15% lake (whole cell, land included) | **lake polygon + 500m shore ring** | v1 inputs were ~37% land overall (43% for small lakes), depending on how the grid happened to fall. |
| Model input | each 1km cell (100px) stretched to 224×224 | 224×224 windows at 30m; **only lake and shore tokens** are encoded | Correct scale. Leaving out the other tokens matches pre-training, where the encoder saw a 25% subset. Checked against the official encoder: identical to 1.4e-6. |
| Selecting pixels | hard 15% cut-off per cell | **weighting by fraction**: each token weighted by its share of cloud-free lake (or shore) pixels | Nothing dropped, no threshold. |
| Pooling | coverage-weighted mean of cell vectors | separate **lake** and **shore** vectors | — |
| Final embedding | single pooled vector | `normalize(0.7·lake + 0.3·shore)` | Keeps the same water/shore balance for every lake regardless of size (pooling lake and ring together would give 82% land for small lakes). |
| Re-weighting | not possible | `POST /embeddings/merge` with `lake_weight` | Recomputes in seconds from the stored parts; no model run, no re-download. |
| Missing pixels | filled with 0, then normalised (large negative values) | filled with the band's training mean (0 after normalisation) | Same as Prithvi's own `inference.py`. |
| Failure handling | — | a failed lake-year has its old vectors **cleared** | Old and new vectors are never compared. |
| Version marker | — | `embedding_version = 2` | v1 rows are identifiable until overwritten. |

### Why a 500m ring
- **Data:** JRC Global Surface Water (Landsat, 1984–2021) across all 829 lakes. Area just outside the HydroLAKES polygon was ever water: 41% at 0–250m, 10% at 250–500m, 2–5% beyond (background ponds and paddy). The lake's own fluctuation zone ends at about 500m.
- **Literature:** near-shore land-use effects on lake water quality are most often reported at 100–500m (e.g. Florida lakes at 100/500m; a reservoir study at 200m). Some indicators reach 1km. Effects beyond that are catchment hydrology, which a ring can't capture.
- **Resolution:** at 30m a token is 480m, so 500m is the narrowest ring that forms a separate region.

### Why a 0.7 / 0.3 weight
No published weight exists for this. The forecast targets water state, which the lake pixels observe directly; shoreline land use is a secondary driver. 0.7/0.3 is the starting point. **Plan:** after the run, sweep the weight from 0 to 1 using the existing backtest and choose the best. This only re-blends stored vectors.

## 7. Database schema

| Migration | Change | Reason |
|---|---|---|
| 021 | `lake_features`: `b1_*`, `b8a_*`, `b11_*`, `b12_*` (mean, std, min, max, median), `clear_obs_mean / min / median` | Full band stack and composite quality. |
| 022 | `regions`: `lake_embedding`, `shore_embedding`, `lake_weight`, `lake_token_weight`, `shore_token_weight`, `tokens_encoded`, `embedding_version` (indexed) | Store the parts for re-weighting, plus provenance. `regions.embedding` is still the single vector used everywhere. |
| 023 | dropped `sub_regions` (233,002 rows, ~2 GB) | The 1km-cell table is no longer used. Local database went from ~2 GB to 125 MB. |

## 8. Pipeline reliability

| Problem in version 1 | Effect on a full re-run | Version 2 |
|---|---|---|
| Tile rows from the old grid stayed `COMPLETED` | old tiles reused or mixed with new ones | Old-grid rows deleted; tiles whose bounds changed are reset; a tile counts only if its file is the current 12-band 30m stack. |
| Merge used whatever tiles existed | lake images with holes, no error | Every tile must be complete and current, or the merge fails clearly. |
| Features skipped any `completed` row; saved with a plain INSERT | all lakes kept v1 features; recomputing would hit a duplicate-key error | Skip only `feature_version = 2`; always upsert. |
| No resume for merge; tiles needed after merge | reruns re-merged everything; with `delete_tiles=True`, re-downloaded everything | Download and merge skip lake-years whose merged image is already current. |
| Image paths resolved differently by different steps | features and embeddings fail when images live on another drive | One shared path resolver. |
| Merge and features ran on every lake | couldn't be run on part of the data | Optional `lake_ids` filter. |

## 9. Removed code
- 1km-cell embedding modules: `grid_generator.py`, `cell_extractor.py`, `weighted_pooling.py`, `lake_aggregator.py`.
- Legacy unused pipeline: `ML_pipeline/pipeline.py`, `gee_ingest.py`, `classifier.py`, plus the single-patch inference in `prithvi_inference.py` (now only the model loader).
- `SubRegion` / `SubRegionFeature` models and their test.
- `sub_regions` creation in the sync flow; sync now selects active lakes directly.

## 10. Dependencies

| File | Change | Reason |
|---|---|---|
| `requirements-ml.txt` | added `torchvision`, `timm`, `einops`, PyTorch CPU index; removed `transformers`, `scikit-learn`, `pandas` | Prithvi's code imports `timm` and `einops` (it could not load on the dev machine); the removed packages are imported nowhere. |
| `requirements.txt` | added `numpy`, `pillow`; `rasterio` pinned to 1.3.10 (was 1.4.3) | Core code imports numpy and PIL directly; 1.3.10 is the installed and tested version. |

All pins match the project `.venv`, and `pip check` is clean.

## 11. Verification

| Check | Result |
|---|---|
| Live download (smallest lake, 2016) | 12 bands, uint16, 30.0m, 12 clear observations per pixel |
| v2 vs v1 band medians, same lake | within ~1–3% |
| Token-subset encoder vs official Prithvi | max difference 1.4e-6 |
| End-to-end: download → merge → features → embeddings | 3 lake-years (incl. Rihand, 5 tiles) succeeded |
| Rerun after completion, including with tiles deleted | every stage skipped; nothing re-downloaded |
| Speed on CPU | embeddings 0.2s (small lake) to ~4s (Rihand); download 23–60s per lake-year |
| Memory | ~1.2 GB peak, almost all of it the Prithvi model |
| Unit tests | 6 pass. The remaining failures are pre-existing and fail identically on the untouched code. |

## 12. Before the full run
1. **Disk space:** up to ~30 GB of merged images (~61 GB if tiles are kept). Set `SENTINEL_DATA_DIR` to a drive with room and merge with `delete_tiles=True`.
2. **Database target:** `backend/.env` has `DATABASE_URL_OVERRIDE` pointing to Supabase. For a local run, blank it out (e.g. `DATABASE_URL_OVERRIDE= POSTGRES_HOST=localhost`). Supabase also needs `alembic upgrade head` before use; that drops `sub_regions` there too.
3. **Open feature decisions** (each needs only a `FEATURE_VERSION` bump and a local recompute, no new download):
   - water rule `MNDWI > 0` only (the extra NDWI/NDVI branch was tuned for the old stand-in SWIR);
   - shrink the lake polygon inward by 60m for water-quality statistics;
   - NDCI and turbidity from water pixels only;
   - Red Edge Slope uses a different unit from the shared 0.005 forecast threshold.
4. **Run order:** Fetch Images → Merge → Generate Features → Generate Embeddings. Later: calibrate the lake/shore weight and re-blend.
