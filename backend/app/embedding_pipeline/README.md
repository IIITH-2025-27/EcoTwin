# Lake embedding generation from multiple lake tiles

This pipeline creates one embedding per lake and year by combining embeddings from many smaller lake tiles (also called cells or sub-regions).

## Overview

For each lake/year pair, the system:

1. Finds the relevant GeoTIFF for that lake and year.
2. Reads the lake polygon from PostGIS.
3. Splits the lake footprint into a grid of spatial cells.
4. Extracts a raster patch for each cell.
5. Runs the Prithvi model on each cell to generate a feature embedding.
6. Stores each cell embedding in the `sub_regions` table.
7. Aggregates all valid cell embeddings into one lake-level embedding.
8. Stores the final lake embedding in the `regions` table on the matching lake/region row.

## Why multiple tiles are used

A lake is often larger than a single image patch. Using multiple tiles lets the model capture spatial variation across the lake rather than compressing everything into one patch. The final lake embedding is therefore a summary of the whole lake surface, not just a single region.

## End-to-end flow

```text
GeoTIFF + lake polygon
    -> generate grid cells / tiles
    -> extract raster for each tile
    -> run Prithvi inference
    -> save cell embeddings in sub_regions
    -> aggregate tile embeddings into one lake embedding
    -> save lake embedding in lake_embeddings
```

## How the per-lake embedding is built

For each `(lake_id, year)` pair, the pipeline collects all completed tile embeddings that:

- have `status = 'completed'`
- are not `NULL`
- have a positive `coverage_percent`

Each tile contributes with its coverage percentage as a weight. The final embedding is computed as a coverage-weighted mean of the tile embeddings, followed by L2 normalization.

This is implemented in the aggregation step using:

- `weighted_mean_pool(...)` for the weighted aggregation
- `aggregate_single_lake_year(...)` for one lake/year pair
- `aggregate_all_lake_embeddings(...)` for batch processing

## Storage model

### Cell-level embeddings

Cell embeddings are stored in `sub_regions` with metadata such as:

- `lake_id`
- `year`
- `cell_number`
- `coverage_percent`
- `embedding`
- `status`
- `error_message`

### Lake-level embeddings

The aggregated result is stored in `regions` as one row per `(lake_id, year)` with the embedding plus metadata such as `coverage_percent`, `num_cells`, `status`, and the lake identifier.

## Notes on quality control

The aggregation step skips invalid contributions:

- embeddings with the wrong dimension
- embeddings containing `NaN` or `Inf`
- zero vectors
- rows with zero or negative coverage

If no valid tile embeddings are found, the lake/year pair is skipped.

## How to run

### Full pipeline

Use the main embedding pipeline entrypoint to process lakes and years.

### Aggregation only

To aggregate already-generated tile embeddings into lake embeddings:

```bash
python -m app.embedding_pipeline.lake_aggregator
```

You can also call the aggregation functions from application code:

```python
from app.embedding_pipeline.lake_aggregator import aggregate_all_lake_embeddings

aggregate_all_lake_embeddings()
```

## Summary

Each lake embedding is created by combining many tile-level embeddings from the lake surface. The system uses coverage-weighted pooling so that tiles covering more of the lake have a stronger influence on the final representation.
