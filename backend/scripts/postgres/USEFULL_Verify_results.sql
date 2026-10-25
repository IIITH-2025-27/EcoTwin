-- Per-year pipeline counts: lakes → tiles → images → embeddings → features,
-- plus consistency checks. Rows are listed in pipeline order.
--
--   lake_images.status   completed = tiles downloaded, not merged yet
--                        merged    = merged GeoTIFF exists (input for the next steps)
--                        failed    = download failed (e.g. no Sentinel-2 L2A scenes)
--   regions              embedding_version 2 = lake + shore Prithvi embedding (current)
--   lake_features        feature_version   2 = 30 m, B1–B12 stack (current)
--
-- The "check_*" rows should be 0 once a year is fully processed.

DROP FUNCTION IF EXISTS verify_counts(INT[]);

CREATE OR REPLACE FUNCTION verify_counts(p_years INT[])
RETURNS TABLE (
    table_name TEXT,
    "2016" BIGINT,
    "2017" BIGINT,
    "2018" BIGINT,
    "2019" BIGINT,
    "2020" BIGINT,
    "2021" BIGINT,
    "2022" BIGINT,
    "2023" BIGINT,
    "2024" BIGINT,
    "2025" BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    i INT;
    m RECORD;
BEGIN
    DROP TABLE IF EXISTS tmp_verify_counts;
    CREATE TEMP TABLE tmp_verify_counts (
        ord INT,
        table_name TEXT PRIMARY KEY,
        "2016" BIGINT,
        "2017" BIGINT,
        "2018" BIGINT,
        "2019" BIGINT,
        "2020" BIGINT,
        "2021" BIGINT,
        "2022" BIGINT,
        "2023" BIGINT,
        "2024" BIGINT,
        "2025" BIGINT
    ) ON COMMIT DROP;

    -- (order, row name, query; %1$s = year)
    DROP TABLE IF EXISTS tmp_verify_metrics;
    CREATE TEMP TABLE tmp_verify_metrics (ord INT, name TEXT, q TEXT) ON COMMIT DROP;
    INSERT INTO tmp_verify_metrics VALUES
        -- Tiles
        (10, 'lake_tiles_completed',
             'SELECT COUNT(*) FROM lake_tiles WHERE year=%1$s AND status=''COMPLETED'''),
        (11, 'lake_tiles_not_completed',
             'SELECT COUNT(*) FROM lake_tiles WHERE year=%1$s AND status<>''COMPLETED'''),

        -- Images
        (20, 'lake_images_downloaded_not_merged',
             'SELECT COUNT(*) FROM lake_images WHERE year=%1$s AND status=''completed'''),
        (21, 'lake_images_merged',
             'SELECT COUNT(*) FROM lake_images WHERE year=%1$s AND status=''merged'''),
        (22, 'lake_images_failed',
             'SELECT COUNT(*) FROM lake_images WHERE year=%1$s AND status NOT IN (''completed'',''merged'')'),

        -- Embeddings
        (30, 'regions_v2_completed',
             'SELECT COUNT(*) FROM regions WHERE year=%1$s AND embedding_version=2 AND status=''completed''
                AND embedding IS NOT NULL AND lake_embedding IS NOT NULL'),
        (31, 'regions_v2_with_shore',
             'SELECT COUNT(*) FROM regions WHERE year=%1$s AND embedding_version=2 AND status=''completed''
                AND shore_embedding IS NOT NULL'),
        (32, 'regions_v2_lake_weights_distinct',
             'SELECT COUNT(DISTINCT lake_weight) FROM regions WHERE year=%1$s AND embedding_version=2
                AND status=''completed'' AND shore_embedding IS NOT NULL'),
        (33, 'regions_failed',
             'SELECT COUNT(*) FROM regions WHERE year=%1$s AND (status<>''completed'' OR embedding IS NULL)'),
        (34, 'regions_legacy_v1',
             'SELECT COUNT(*) FROM regions WHERE year=%1$s AND COALESCE(embedding_version,1)<2'),

        -- Features
        (40, 'lake_features_v2_completed',
             'SELECT COUNT(*) FROM lake_features WHERE year=%1$s AND status=''completed'' AND feature_version=2'),
        (41, 'lake_features_failed',
             'SELECT COUNT(*) FROM lake_features WHERE year=%1$s AND status<>''completed'''),
        (42, 'lake_features_legacy_v1',
             'SELECT COUNT(*) FROM lake_features WHERE year=%1$s AND status=''completed'' AND COALESCE(feature_version,1)<2'),

        -- Consistency (should be 0)
        (50, 'check_merged_without_embedding',
             'SELECT COUNT(*) FROM lake_images li WHERE li.year=%1$s AND li.status=''merged''
                AND NOT EXISTS (SELECT 1 FROM regions r WHERE r.lake_id=li.lake_id AND r.year=li.year
                                AND r.embedding_version=2 AND r.status=''completed'')'),
        (51, 'check_merged_without_features',
             'SELECT COUNT(*) FROM lake_images li WHERE li.year=%1$s AND li.status=''merged''
                AND NOT EXISTS (SELECT 1 FROM lake_features f WHERE f.lake_id=li.lake_id AND f.year=li.year
                                AND f.status=''completed'' AND f.feature_version=2)'),
        (52, 'check_embedding_without_merged_image',
             'SELECT COUNT(*) FROM regions r WHERE r.year=%1$s AND r.embedding_version=2 AND r.status=''completed''
                AND NOT EXISTS (SELECT 1 FROM lake_images li WHERE li.lake_id=r.lake_id AND li.year=r.year
                                AND li.status=''merged'')'),
        (53, 'check_features_without_merged_image',
             'SELECT COUNT(*) FROM lake_features f WHERE f.year=%1$s AND f.status=''completed''
                AND NOT EXISTS (SELECT 1 FROM lake_images li WHERE li.lake_id=f.lake_id AND li.year=f.year
                                AND li.status=''merged'')'),
        (54, 'check_active_lakes_without_image',
             'SELECT COUNT(*) FROM lakes l WHERE l.is_active
                AND NOT EXISTS (SELECT 1 FROM lake_images li WHERE li.lake_id=l.lake_id AND li.year=%1$s)');

    INSERT INTO tmp_verify_counts(ord, table_name)
    SELECT 0, 'lakes_active'
    UNION ALL
    SELECT ord, name FROM tmp_verify_metrics;

    FOR i IN 1..array_length(p_years, 1)
    LOOP
        -- Active lakes (same for every year)
        EXECUTE format(
            'UPDATE tmp_verify_counts SET "%1$s" = (SELECT COUNT(*) FROM lakes WHERE is_active)
             WHERE table_name = ''lakes_active'';',
            p_years[i]);

        FOR m IN SELECT * FROM tmp_verify_metrics
        LOOP
            EXECUTE format(
                'UPDATE tmp_verify_counts SET "%1$s" = (' || m.q || ') WHERE table_name = %2$L;',
                p_years[i], m.name);
        END LOOP;
    END LOOP;

    RETURN QUERY
    SELECT t.table_name, t."2016", t."2017", t."2018", t."2019", t."2020",
           t."2021", t."2022", t."2023", t."2024", t."2025"
    FROM tmp_verify_counts t
    ORDER BY t.ord;
END;
$$;


-- SELECT * FROM verify_counts(ARRAY[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]);
