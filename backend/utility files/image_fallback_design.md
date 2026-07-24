````markdown
# Sentinel-2 Collection Fallback Design

## Overview

This document describes the issue encountered while generating Sentinel-2 composites for lake tiles, the investigation performed, the chosen solution, and its impact on the existing EcoTwin imagery pipeline.

---

# Problem Statement

The imagery pipeline currently uses only the following Earth Engine dataset:

```text
COPERNICUS/S2_SR_HARMONIZED
```

During image generation, a number of lake-year combinations (primarily in **2016** and a few in **2017**) failed with the following error:

```text
Image.select: Band pattern 'B2' was applied to an Image with no bands.
```

Initially this appeared to be a band selection issue.

However, detailed logging showed that the actual problem occurred much earlier in the pipeline.

Example:

```text
Raw collection: 0
Filtered collection: 0
```

The ImageCollection itself was empty before cloud masking or compositing.

---

# Investigation

The affected Area of Interest (AOI) was tested directly in the Google Earth Engine Code Editor.

The following collections were compared:

- COPERNICUS/S2
- COPERNICUS/S2_SR
- COPERNICUS/S2_SR_HARMONIZED

Results:

| Collection | Images Found |
|------------|-------------:|
| COPERNICUS/S2 | 37 |
| COPERNICUS/S2_SR | 0 |
| COPERNICUS/S2_SR_HARMONIZED | 0 |

The Level-1C collection clearly contained imagery throughout 2016, while the Surface Reflectance collections contained none.

Further year-wise verification showed:

| Year | SR_HARMONIZED Images |
|------|----------------------:|
| 2016 | 0 |
| 2017 | 2 |
| 2018 | 7 |
| 2019 | 74 |
| 2020 | 73 |
| 2021 | 72 |
| 2022 | 73 |
| 2023 | 74 |
| 2024 | 75 |
| 2025 | 86 |

This confirmed that the issue is caused by **dataset availability**, not by the processing pipeline.

---

# Root Cause

The current pipeline assumes that every requested year is available in:

```text
COPERNICUS/S2_SR_HARMONIZED
```

This assumption is incorrect.

For early Sentinel-2 years (particularly 2016), Surface Reflectance imagery is unavailable for many locations, while Level-1C imagery exists.

As a result:

```
Empty ImageCollection
        ↓
Median Composite
        ↓
Image with no bands
        ↓
Band selection failure
```

---

# Solution

Implement an automatic collection fallback.

## Primary Collection

```text
COPERNICUS/S2_SR_HARMONIZED
```

This remains the default collection.

No existing processing behaviour changes.

## Fallback Collection

If the filtered SR_HARMONIZED ImageCollection is empty:

```text
COPERNICUS/S2
```

is automatically used instead.

Processing then continues normally.

---

# Processing Flow

```text
Load SR_HARMONIZED
        │
        ▼
Filter AOI + Date
        │
        ▼
Collection Empty?
        │
 ┌──────┴──────┐
 │             │
No            Yes
 │             │
 ▼             ▼
Use SR      Switch to S2
 │             │
 ▼             ▼
Apply Cloud Mask
 │
 ▼
Composite
 │
 ▼
Export Tile
```

---

# Cloud Masking

The two collections require different cloud masking methods.

## SR_HARMONIZED

Uses the existing SCL-based cloud masking implementation.

```
SCL band
```

No changes required.

## S2

Since Level-1C does not contain the SCL band, the fallback path uses QA60-based cloud masking.

This ensures cloud masking remains enabled for both collections.

---

# Database Changes

The `lake_tiles` table now includes:

```sql
collection_used TEXT
```

Default value:

```text
COPERNICUS/S2_SR_HARMONIZED
```

Only fallback records update this value to:

```text
COPERNICUS/S2
```

Example:

| lake_id | year | tile | collection_used |
|---------|------|------|-----------------|
| 1509 | 2019 | 0_0 | COPERNICUS/S2_SR_HARMONIZED |
| 1509 | 2016 | 0_0 | COPERNICUS/S2 |

No additional boolean flag is required since the collection itself identifies fallback records.

---

# Logging

Normal processing:

```text
INFO Using collection: COPERNICUS/S2_SR_HARMONIZED
```

Fallback:

```text
WARNING No SR_HARMONIZED imagery found for lake_id=1509 year=2016.
WARNING Falling back to COPERNICUS/S2.
```

This provides complete traceability for every generated tile.

---

# Justification

This approach was selected for several reasons:

## 1. Maximum Data Coverage

Without fallback, all lake-years lacking SR imagery fail.

With fallback, imagery can still be generated using Level-1C.

---

## 2. Preserve Existing Dataset

Most previously generated imagery already uses:

```text
COPERNICUS/S2_SR_HARMONIZED
```

Keeping SR_HARMONIZED as the default avoids unnecessary regeneration.

---

## 3. Minimal Pipeline Changes

Only the collection selection logic changes.

The remaining processing pipeline (compositing, export, tiling, embedding generation) remains unchanged.

---

## 4. Future Traceability

Each generated tile records the collection used.

This enables:

- auditing
- debugging
- selective reprocessing
- future dataset upgrades

without ambiguity.

---

## Impact Assessment

### Existing Data

No impact.

Existing rows already default to:

```text
COPERNICUS/S2_SR_HARMONIZED
```

No migration of historical data is required.

---

### New Processing

Only lake-years with missing SR imagery use the fallback.

All other processing continues exactly as before.

---

### Embedding Quality

Surface Reflectance (SR_HARMONIZED) remains the preferred source.

Fallback imagery (Level-1C) may introduce a small atmospheric domain shift because it represents Top-of-Atmosphere reflectance rather than Surface Reflectance.

However:

- Spatial resolution is unchanged.
- Spectral bands remain identical.
- Coverage is preserved.

The small potential difference in embedding quality is considered preferable to having missing embeddings.

---

# Benefits

- Automatic recovery from missing SR imagery.
- Complete processing for early Sentinel-2 years.
- No impact on existing data.
- Full backward compatibility.
- Minimal code changes.
- Reproducible and traceable processing.
- Easy identification of fallback-generated imagery.

---

# Final Decision

The pipeline will continue using:

```text
COPERNICUS/S2_SR_HARMONIZED
```

as the primary dataset.

Whenever the filtered ImageCollection is empty, the pipeline will automatically switch to:

```text
COPERNICUS/S2
```

for that lake-year only.

The actual collection used will be recorded in the `lake_tiles.collection_used` column, ensuring complete provenance while maximizing imagery availability.
````
