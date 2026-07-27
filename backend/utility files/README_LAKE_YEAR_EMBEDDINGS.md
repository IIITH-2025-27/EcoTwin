# Lake-Year Embeddings

`regions` is the final-output table for lake embeddings. It holds exactly one
coverage-weighted, L2-normalized `vector(768)` embedding for each
`(lake_id, year)` pair.

## Table design

The table uses `PRIMARY KEY (lake_id, year)` and contains:

`lake_id`, `year`, `center_lat`, `center_lon`, `created_at`, `updated_at`,
`embedding`, `status`, and `error_message`.

The row is created when completed cell embeddings are available. Re-running an
aggregation replaces the existing embedding for the same lake and year; it
never creates a duplicate row.

## Changed files

- `alembic/versions/013_rebuild_regions_as_lake_year_embeddings.py` drops the
  former UUID-based `regions` table and creates the lake-year output table.
- `app/models/region.py` maps the new composite key and the final embedding
  fields.
- `app/embedding_pipeline/lake_aggregator.py` reads completed cell embeddings,
  weights each by `sub_regions.coverage_percent`, pools them, L2-normalizes the
  result, and upserts it into `regions`.
- `app/embedding_pipeline/storage.py` uses the same lake-year upsert when the
  main embedding pipeline performs aggregation.
- `app/models/embedding.py`, `app/models/temporal_profile.py`, and
  `app/models/report.py` remove obsolete ORM relationships to the deleted UUID
  key. The legacy tables remain, but their former foreign-key constraints are
  removed by the migration.

## Run on another laptop

1. Clone the repository and create a Python 3.12 virtual environment:

   ```bash
   cd backend
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```

   Set strong values for `POSTGRES_PASSWORD` and `SECRET_KEY`. Keep
   `POSTGRES_HOST=localhost` and `REDIS_HOST=localhost` for local services.
2. Start local PostgreSQL with PostGIS and pgvector enabled, then apply
   migrations:

   ```bash
   alembic upgrade head
   ```

   The `013` migration intentionally drops and recreates `regions`; do not run
   it against a database whose old UUID-based region records must be retained.
3. Import lake geometries and generate completed `sub_regions` embeddings using
   the normal sync and embedding pipeline. The aggregate command only processes
   cells with `status = 'completed'`, a non-null 768-dimensional embedding, and
   positive coverage.
4. Create or refresh common lake embeddings:

   ```bash
   python -m app.embedding_pipeline.lake_aggregator \
     --lake-ids 1400 --years 2016
   ```

   Omit both arguments to aggregate every eligible lake-year pair.
5. Verify the output:

   ```bash
   psql -U ecotwin -d ecotwin -c \
     "SELECT lake_id, year, vector_dims(embedding), status FROM regions ORDER BY lake_id, year;"
   ```

Successful rows report `vector_dims = 768` and `status = completed`.
