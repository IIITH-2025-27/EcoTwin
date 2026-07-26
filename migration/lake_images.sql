INSERT INTO lake_images (
    lake_id,
    year,
    file_path,
    status,
    file_size_bytes,
    error_message,
    retry_count,
    created_at,
    updated_at
)
SELECT
    s.lake_id,
    s.year,
    s.file_path,
    s.status,
    s.file_size_bytes,
    s.error_message,
    s.retry_count,
    s.created_at,
    s.updated_at
FROM dblink(
    'host=localhost dbname=ecotwin_ankit user=postgres password=YOUR_PASSWORD',
    $$
    SELECT
        lake_id,
        year,
        file_path,
        status,
        file_size_bytes,
        error_message,
        retry_count,
        created_at,
        updated_at
    FROM lake_images
    $$
) AS s(
    lake_id bigint,
    year integer,
    file_path varchar(512),
    status varchar(20),
    file_size_bytes bigint,
    error_message text,
    retry_count integer,
    created_at timestamptz,
    updated_at timestamptz
)
ON CONFLICT (lake_id, year)
DO NOTHING;