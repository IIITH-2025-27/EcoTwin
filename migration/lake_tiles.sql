INSERT INTO lake_tiles (
    lake_id,
    year,
    tile_index,
    tile_geometry,
    bbox,
    status,
    image_path,
    file_size_bytes,
    error_message,
    retry_count,
    created_at,
    updated_at
)
SELECT
    t.lake_id,
    t.year,
    t.tile_index,
    t.tile_geometry,
    t.bbox,
    t.status,
    t.image_path,
    t.file_size_bytes,
    t.error_message,
    t.retry_count,
    t.created_at,
    t.updated_at
FROM dblink(
    'host=localhost dbname=ecotwin_ankit user=postgres password=YOUR_PASSWORD',
    $$
    SELECT
        lake_id,
        year,
        tile_index,
        tile_geometry,
        bbox,
        status,
        image_path,
        file_size_bytes,
        error_message,
        retry_count,
        created_at,
        updated_at
    FROM lake_tiles
    $$
) AS t(
    lake_id BIGINT,
    year INTEGER,
    tile_index VARCHAR(20),
    tile_geometry geometry(POLYGON,4326),
    bbox VARCHAR(200),
    status VARCHAR(20),
    image_path TEXT,
    file_size_bytes BIGINT,
    error_message TEXT,
    retry_count INTEGER,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)
ON CONFLICT (lake_id, year, tile_index)
DO NOTHING;