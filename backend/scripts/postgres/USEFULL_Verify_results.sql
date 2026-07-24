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
BEGIN
    CREATE TEMP TABLE tmp_verify_counts (
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

    INSERT INTO tmp_verify_counts(table_name)
    VALUES
        ('lakes_Active'),
        ('lake_tiles_COMPLETED'),
        ('lake_tiles_FAILED'),
        ('lake_images_COMPLETED'),
        ('lake_images_FAILED'),
        ('lake_images_MERGED'),
        ('sub_regions_completed'),
		('sub_regions_failed'),
        ('sub_regions_lake_count');

    FOR i IN 1..array_length(p_years,1)
    LOOP

        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM lake_tiles
                 WHERE year=%1$s
                 AND status=''COMPLETED''
             )
             WHERE table_name=''lake_tiles_COMPLETED'';',
            p_years[i]);

        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM lake_tiles
                 WHERE year=%1$s
                 AND status<>''COMPLETED''
             )
             WHERE table_name=''lake_tiles_FAILED'';',
            p_years[i]);

        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM lake_images
                 WHERE year=%1$s
                 AND status=''completed''
             )
             WHERE table_name=''lake_images_COMPLETED'';',
            p_years[i]);

        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM lake_images
                 WHERE year=%1$s
                 AND status NOT IN (''completed'',''merged'')
             )
             WHERE table_name=''lake_images_FAILED'';',
            p_years[i]);

        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM lake_images
                 WHERE year=%1$s
                 AND status=''merged''
             )
             WHERE table_name=''lake_images_MERGED'';',
            p_years[i]);

        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM sub_regions
                 WHERE year=%1$s
                 AND status=''completed''
				 And embedding is not null
             )
             WHERE table_name=''sub_regions_completed'' ;',
            p_years[i]);
		EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(*)
                 FROM sub_regions
                 WHERE year=%1$s
                 AND status<>''completed''
				 OR embedding is null
             )
             WHERE table_name=''sub_regions_failed'';',
            p_years[i]);
        EXECUTE format(
            'UPDATE tmp_verify_counts
             SET "%1$s" = (
                 SELECT COUNT(DISTINCT lake_id)
                 FROM sub_regions
                 WHERE year=%1$s
                   AND status=''completed''
                   AND embedding IS NOT NULL
             )
             WHERE table_name=''sub_regions_lake_count'';',
            p_years[i]);

    END LOOP;


	
    -- lakes (same for all years)
    UPDATE tmp_verify_counts t
    SET
        "2016" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2017" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2018" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2019" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2020" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2021" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2022" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2023" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2024" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE),
        "2025" = (SELECT COUNT(*) FROM lakes WHERE is_active = TRUE)
    WHERE t.table_name = 'lakes_Active';

    RETURN QUERY
    SELECT t.*
    FROM tmp_verify_counts t
    ORDER BY t.table_name;

END;
$$;


-- SELECT * FROM verify_counts(ARRAY[2023,2024,2025]);