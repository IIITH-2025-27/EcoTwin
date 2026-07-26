# EcoTwin ETL Execution Guide

## Prerequisites

1.  Restore the source databases (`ecotwin_ankit`, `ecotwin_peeyush`).
2.  Ensure the destination database is `ecotwin`.
3.  Connect to the destination database.

``` sql
CREATE EXTENSION IF NOT EXISTS dblink;
```

Verify it
``` sql
SELECT extname
FROM pg_extension
WHERE extname = 'dblink';
```

------------------------------------------------------------------------

## ETL Execution Order

``` text
1. lakes
2. lake_images
3. lake_tiles
4. sub_regions
```

Always run the ETLs in the above order.

------------------------------------------------------------------------

## Running an ETL

1.  Open **pgAdmin**.
2.  Select the **ecotwin** database.
3.  Open **Tools → Query Tool**.
4.  Paste the ETL SQL.
5.  Click **Execute (▶)**.

Expected output:

``` text
INSERT 0 <number_of_rows>
```

If you see:

``` text
INSERT 0 0
```

all rows already exist (because `ON CONFLICT DO NOTHING` skipped
duplicates).

------------------------------------------------------------------------

## Verification Queries

### Total Counts

``` sql
SELECT COUNT(*) FROM lakes;

SELECT COUNT(*) FROM lake_images;

SELECT COUNT(*) FROM lake_tiles;

SELECT COUNT(*) FROM sub_regions;
```

### Counts by Year

``` sql
SELECT year, COUNT(*)
FROM lake_images
GROUP BY year
ORDER BY year;
```

``` sql
SELECT year, COUNT(*)
FROM lake_tiles
GROUP BY year
ORDER BY year;
```

``` sql
SELECT year, COUNT(*)
FROM sub_regions
GROUP BY year
ORDER BY year;
```

------------------------------------------------------------------------

## Import from Multiple Databases

Run the complete ETL sequence for:

-   `ecotwin_ankit`
-   `ecotwin_peeyush`

The only change required is the `dbname` in the `dblink()` connection
string.

Example:

``` text
dbname=ecotwin_ankit
```

then

``` text
dbname=ecotwin_peeyush
```

------------------------------------------------------------------------

## Final Validation

``` sql
SELECT
    (SELECT COUNT(*) FROM lakes) AS lakes,
    (SELECT COUNT(*) FROM lake_images) AS lake_images,
    (SELECT COUNT(*) FROM lake_tiles) AS lake_tiles,
    (SELECT COUNT(*) FROM sub_regions) AS sub_regions;
```

If the counts match the expected totals from the source databases, the
ETL migration is complete.
