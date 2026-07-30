import { useQuery } from '@tanstack/react-query';
import { getAnalogs } from '@/api/similarity';
import type { SimilarityMethod, SimilarityResponse } from '@/types';

function emptySimilarityResponse(
  regionId: string,
  method: SimilarityMethod,
  year?: number,
): SimilarityResponse {
  return {
    query_region_id: regionId,
    query_year: year ?? 0,
    analogs: [],
    search_latency_ms: 0,
    method,
  };
}

function isMissingSimilarityData(error: unknown): boolean {
  return error instanceof Error && /(Embedding|Region) not found/i.test(error.message);
}

export function useSimilarity(
  regionId: string | null,
  topK: number = 10,
  year?: number,
  method: SimilarityMethod = 'cosine',
) {
  return useQuery({
    queryKey: ['similarity', regionId, topK, year, method],
    queryFn: async () => {
      try {
        const result = await getAnalogs(regionId!, topK, year, method);
        console.debug(
          '[useSimilarity] Results received:',
          result.analogs.length,
          'analogs, latency:',
          result.search_latency_ms.toFixed(0),
          'ms',
        );
        return result;
      } catch (error) {
        console.warn('[useSimilarity] Error fetching analogs:', error);
        // Only swallow genuine "data not found" errors (404)
        if (regionId && isMissingSimilarityData(error)) {
          return emptySimilarityResponse(regionId, method, year);
        }

        throw error;
      }
    },
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
