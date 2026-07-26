INSERT INTO sub_regions (
    sub_region_id,
    lake_id,
    cell_number,
    year,
    coverage_percent,
    center_lat,
    center_lon,
    geom,
    embedding,
    created_at,
    updated_at,
    status,
    error_message
)
SELECT
    gen_random_uuid(),
    s.lake_id,
    s.cell_number,
    s.year,
    s.coverage_percent,
    s.center_lat,
    s.center_lon,
    s.geom,
    s.embedding,
    s.created_at,
    s.updated_at,
    s.status,
    s.error_message
FROM dblink(
    'host=localhost dbname=ecotwin_ankit user=postgres password=YOUR_PASSWORD',
    $$
    SELECT
        lake_id,
        cell_number,
        year,
        coverage_percent,
        center_lat,
        center_lon,
        geom,
        embedding,
        created_at,
        updated_at,
        status,
        error_message
    FROM sub_regions
    $$
) AS s(
    lake_id BIGINT,
    cell_number INTEGER,
    year INTEGER,
    coverage_percent DOUBLE PRECISION,
    center_lat DOUBLE PRECISION,
    center_lon DOUBLE PRECISION,
    geom geometry(POLYGON,4326),
    embedding vector(768),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    status VARCHAR(20),
    error_message TEXT
)
ON CONFLICT (lake_id, cell_number, year)
DO NOTHING;