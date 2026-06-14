import { useQuery } from '@tanstack/react-query';
import { getAnalogs } from '@/api/similarity';

export function useSimilarity(
  regionId: string | null,
  topK: number = 10,
  year?: number,
) {
  return useQuery({
    queryKey: ['similarity', regionId, topK, year],
    queryFn: () => getAnalogs(regionId!, topK, year),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000, // 10 minutes (matches server cache TTL)
  });
}
