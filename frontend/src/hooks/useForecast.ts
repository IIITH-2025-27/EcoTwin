import { useQuery } from '@tanstack/react-query';
import { getForecast } from '@/api/forecast';
import type { SimilarityMethod } from '@/types';

export function useForecast(
  regionId: string | null,
  method: SimilarityMethod = 'cosine',
) {
  return useQuery({
    queryKey: ['forecast', regionId, method],
    queryFn: () => getForecast(regionId!, method),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
