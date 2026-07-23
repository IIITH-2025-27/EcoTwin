# PostgreSQL Table Backup & Merge Guide (PostGIS + pgvector)

## Purpose

This guide explains how each team member can:

1.  Export a single PostgreSQL table containing PostGIS geometry and
    pgvector embeddings.
2.  Share the backup.
3.  Merge everyone's data into one central database without losing data
    or creating duplicates.

This approach is recommended for tables containing:

-   PostGIS `geometry`
-   `vector` (pgvector) embeddings
-   UUID columns
-   Large binary/object data

------------------------------------------------------------------------

# Table Structure

Example:

  Column      Type
  ----------- -------------
  id          UUID
  lake_id     Integer
  cell_no     Integer
  year        Integer
  geometry    geometry
  embedding   vector(768)

Recommended uniqueness:

``` sql
ALTER TABLE your_table
ADD CONSTRAINT uq_lake_cell_year
UNIQUE (lake_id, cell_no, year);
```

The UUID can remain the primary key.

The `(lake_id, cell_no, year)` combination represents the logical
identity of a record.

------------------------------------------------------------------------

# Why NOT use CSV?

CSV is not ideal because:

-   geometry must be converted manually
-   vectors become text
-   import requires custom conversion
-   easier to corrupt data

Instead use PostgreSQL's native backup format.

------------------------------------------------------------------------

# Step 1 --- Export the Table

Run:

``` bash
pg_dump \
-U postgres \
-d your_database \
-t your_table \
-F c \
-f your_table.backup
```

Explanation:

-   `-t` exports only one table
-   `-F c` creates PostgreSQL Custom Format
-   `your_table.backup` is the backup file

Example:

``` bash
pg_dump \
-U postgres \
-d ecotwin \
-t lake_embeddings \
-F c \
-f lake_embeddings.backup
```

------------------------------------------------------------------------

# Step 2 --- Share the Backup

Each team member sends:

    lake_embeddings.backup

No CSV conversion required.

------------------------------------------------------------------------

# Step 3 --- Create Temporary Table

On the central database:

``` sql
CREATE TABLE lake_embeddings_import
(LIKE lake_embeddings INCLUDING ALL);
```

------------------------------------------------------------------------

# Step 4 --- Restore Backup

``` bash
pg_restore \
-U postgres \
-d ecotwin \
--data-only \
-t lake_embeddings_import \
lake_embeddings.backup
```

If needed, restore into a temporary database first and then copy the
rows into the import table.

------------------------------------------------------------------------

# Step 5 --- Merge Data

``` sql
INSERT INTO lake_embeddings
SELECT *
FROM lake_embeddings_import
ON CONFLICT (lake_id, cell_no, year)
DO NOTHING;
```

This inserts only new records.

------------------------------------------------------------------------

# Updating Existing Records

If newer data should replace old data:

``` sql
INSERT INTO lake_embeddings
SELECT *
FROM lake_embeddings_import
ON CONFLICT (lake_id, cell_no, year)
DO UPDATE
SET
    embedding = EXCLUDED.embedding,
    geometry = EXCLUDED.geometry;
```

------------------------------------------------------------------------

# Clean Up

``` sql
DROP TABLE lake_embeddings_import;
```

------------------------------------------------------------------------

# Recommended Workflow

Developer A

↓

Export backup

↓

Developer B

↓

Export backup

↓

Developer C

↓

Export backup

↓

Central Database

↓

Restore into temporary table

↓

Merge

↓

Delete temporary table

------------------------------------------------------------------------

# Best Practices

-   Keep UUID as the primary key.
-   Add a UNIQUE constraint on `(lake_id, cell_no, year)`.
-   Export only the required table.
-   Restore into a temporary table before merging.
-   Use `ON CONFLICT` to prevent duplicates.
-   Keep backups until the merge has been verified.

------------------------------------------------------------------------

# Summary

This workflow:

-   Preserves PostGIS geometries
-   Preserves pgvector embeddings
-   Avoids CSV conversion
-   Prevents duplicate lake/cell/year records
-   Scales well when multiple developers contribute data
