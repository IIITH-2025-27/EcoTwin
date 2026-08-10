DELETE FROM public.lakes;

DELETE FROM public.sub_regions;

DELETE FROM public.sub_region_features;

SELECT * FROM public.lakes ORDER BY lake_id ASC 

UPDATE public.lakes 
SET is_active = false
WHERE area_sqkm < 2;


UPDATE public.lakes 
SET is_active = true
WHERE area_sqkm >= 2;

-- B8 completion visualization status
SELECT lakes.lake_name,lakes.area_sqkm,lf.b8_median, lf.* FROM public.lake_features lf 
left join lakes on lakes.lake_id = lf.lake_id 
where lf.b8_status = 'completed' 
      and lf.year = 2025
