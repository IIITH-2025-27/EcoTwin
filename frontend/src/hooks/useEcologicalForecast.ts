import { useQuery } from '@tanstack/react-query';
import { getEcologicalForecast } from '@/api/forecast';
import type { SimilarityMethod } from '@/types';

export function useEcologicalForecast(
  regionId: string | null,
  method: SimilarityMethod = 'cosine',
  year?: number,
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ['ecologicalForecast', regionId, method, year],
    queryFn: () => getEcologicalForecast(regionId!, method, year),
    enabled: !!regionId && enabled,
    staleTime: 10 * 60 * 1_000,
  });
}
