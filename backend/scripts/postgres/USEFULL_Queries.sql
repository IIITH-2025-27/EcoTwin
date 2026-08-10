DELETE FROM public.lakes;

DELETE FROM public.sub_regions;

DELETE FROM public.sub_region_features;

SELECT * FROM public.lakes ORDER BY lake_id ASC 

UPDATE public.lakes 
SET is_active = false
WHERE area_sqkm <2;