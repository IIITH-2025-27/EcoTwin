import { useQuery } from '@tanstack/react-query';
import { getEcologicalForecast } from '@/api/forecast';
import type { SimilarityMethod } from '@/types';

export function useEcologicalForecast(
  regionId: string | null,
  method: SimilarityMethod = 'cosine',
) {
  return useQuery({
    queryKey: ['ecologicalForecast', regionId, method],
    queryFn: () => getEcologicalForecast(regionId!, method),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
