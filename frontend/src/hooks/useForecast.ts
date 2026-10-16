import { useQuery } from '@tanstack/react-query';
import { getForecast } from '@/api/forecast';
import { trackRequest } from '@/lib/requestStart';
import type { SimilarityMethod } from '@/types';

export const forecastQueryKey = (regionId: string | null, method: SimilarityMethod = 'cosine') =>
  ['forecast', regionId, method] as const;

export function useForecast(
  regionId: string | null,
  method: SimilarityMethod = 'cosine',
) {
  const queryKey = forecastQueryKey(regionId, method);
  return useQuery({
    queryKey,
    queryFn: () => trackRequest(queryKey, () => getForecast(regionId!, method)),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
