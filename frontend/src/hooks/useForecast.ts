import { useQuery } from '@tanstack/react-query';
import { getForecast } from '@/api/forecast';

export function useForecast(regionId: string | null) {
  return useQuery({
    queryKey: ['forecast', regionId],
    queryFn: () => getForecast(regionId!),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
