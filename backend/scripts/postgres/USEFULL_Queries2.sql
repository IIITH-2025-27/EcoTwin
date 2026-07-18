select *  FROM public.lakes where is_active=true
ORDER BY area_sqkm desc 
-- =======================================================================================
-- for checking the lake tile which is not completed
SELECT lakes.lake_name,lakes.area_sqkm,lt.status,lt.created_at,lt.updated_at,lt.error_message,lt.* FROM public.lake_tiles lt
Left Join lakes on lakes.lake_id = lt.lake_id where lt.status != 'COMPLETED'
ORDER BY id ASC 
-- =======================================================================
-- For completed lake count and tiles count
SELECT l.lake_name,count(*), l.area_sqkm  FROM public.lake_images li join lake_tiles lt ON lt.lake_id = li.lake_id 
join lakes l ON l.lake_id = li.lake_id 
GROUP by l.lake_name,l.area_sqkm

-- ================================================================
-- For Comparision of buffered area and number of tile and

SELECT
    l.lake_id,l.lake_name,l.area_sqkm,
    ROUND(
        ( ST_Area( ST_Transform( ST_Buffer( ST_Transform(l.geom, 6933),2000 ),
                    6933 )) / 1000000 )::numeric, 2 ) AS buffered_area_sqkm,
    COUNT(t.tile_index) AS tiles,
    ROUND((l.area_sqkm / COUNT(t.tile_index))::numeric, 2) AS area_per_tile,
    ROUND(
        ( ST_Area( ST_Transform( ST_Buffer( ST_Transform(l.geom, 6933),2000 ),
                    6933 )) / 1000000 / COUNT(t.tile_index) )::numeric, 2
    ) AS buffered_area_per_tile
FROM lakes l
JOIN lake_images li ON li.lake_id = l.lake_id
JOIN lake_tiles t ON t.lake_id = l.lake_id AND t.year = li.year
GROUP BY l.lake_id, l.lake_name, l.area_sqkm,l.geom 
ORDER BY l.area_sqkm DESC;