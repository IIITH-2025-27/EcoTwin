# EcoTwin Data Migration Guide

## Overview

This guide explains how to collect data from team members and safely
migrate it into the production database.

**Recommended approach:**

-   Each team member creates a PostgreSQL custom dump (`.dump`).
-   Restore each dump into a temporary database.
-   Run a Python ETL script to copy and validate the data.
-   Merge the validated data into the production database.
-   Delete the temporary database.

------------------------------------------------------------------------

## Step 1 -- Create a PostgreSQL Dump

Each team member should run:

``` bash
pg_dump \
  -h localhost \
  -U postgres \
  -d ecotwin \
  -Fc \
  -f v5_ecotwin_till_b8.dump
```

This preserves:

-   PostGIS geometries
-   pgvector embeddings
-   Constraints
-   Indexes
-   All PostgreSQL data types

------------------------------------------------------------------------

## Step 2 -- Create a Temporary Database

``` bash
createdb -h localhost -U postgres ecotwin_member1
```

------------------------------------------------------------------------

## Step 3 -- Restore the Dump

``` bash
pg_restore \
  -h localhost \
  -U postgres \
  -d ecotwin_member1 \
  ecotwin_ankit.dump

# /usr/lib/postgresql/17/bin/pg_restore     -h localhost     -U postgres     -O -x     -d ecotwin_peeyush     ecotwin_peeyush.dum
```

The temporary database now contains the teammate's data.

------------------------------------------------------------------------

## Step 4 -- Configure `postgres_fdw`

Enable the extension in the production database.

``` sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
```

Create a connection to the temporary database.

``` sql
CREATE SERVER member1_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'localhost',
    dbname 'ecotwin_member1',
    port '5432'
);
```

Create a user mapping.

``` sql
CREATE USER MAPPING
FOR CURRENT_USER
SERVER member1_server
OPTIONS (
    user 'postgres',
    password 'your_password'
);
```

Create a schema to hold the foreign tables.

``` sql
CREATE SCHEMA member1_fdw;
```

Import all tables from the temporary database.

``` sql
IMPORT FOREIGN SCHEMA public
FROM SERVER member1_server
INTO member1_fdw;
```

After this step, all tables from `ecotwin_member1` will be available
under the `member1_fdw` schema.

------------------------------------------------------------------------

## Step 5 -- Validate

Validate the imported temporary tables before merging.

-   Compare row counts with the source database.
-   Check for duplicate records.
-   Validate geometries using `ST_IsValid`.
-   Verify embedding dimensions.
-   Check for NULL embeddings.
-   Verify foreign-key consistency.

------------------------------------------------------------------------

## Step 6 -- Merge into Production

After successful validation, merge the temporary tables into the
production tables.

``` sql
INSERT INTO lake_embeddings
SELECT *
FROM member1_lake_embeddings
ON CONFLICT (...) DO UPDATE
SET ...;
```

Repeat for the remaining tables.

------------------------------------------------------------------------

## Step 7 -- Cleanup

Remove the temporary resources after the migration.

``` sql
DROP TABLE IF EXISTS
    member1_lake_embeddings,
    member1_lake_tiles,
    member1_lake_images;

DROP SCHEMA member1_fdw CASCADE;
DROP SERVER member1_server CASCADE;
```

Finally, remove the temporary database.

``` bash
dropdb -h localhost -U postgres ecotwin_member1
```

------------------------------------------------------------------------

## Architecture

``` text
member1.dump
      │
      ▼
Restore
      │
      ▼
ecotwin_member1
      │
      ▼
postgres_fdw
      │
      ▼
member1_fdw.*
      │
      ▼
Validation
      │
      ▼
Production Tables
      │
      ▼
Cleanup
```

------------------------------------------------------------------------

## Advantages

-   Uses the official PostgreSQL `postgres_fdw` extension.
-   No CSV export/import required.
-   Preserves PostGIS geometries, pgvector embeddings, JSONB, arrays,
    UUIDs and all PostgreSQL data types.
-   No Python ETL is required for copying data.
-   Easy to automate for multiple team members.
-   Temporary tables allow validation before merging into production.