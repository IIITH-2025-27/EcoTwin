import { useQuery } from '@tanstack/react-query';
import { getAnalogs } from '@/api/similarity';
import type { SimilarityMethod } from '@/types';

export function useSimilarity(
  regionId: string | null,
  topK: number = 10,
  year?: number,
  method: SimilarityMethod = 'cosine',
) {
  return useQuery({
    queryKey: ['similarity', regionId, topK, year, method],
    queryFn: () => getAnalogs(regionId!, topK, year, method),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
