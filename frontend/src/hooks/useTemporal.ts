import { useQuery } from '@tanstack/react-query';
import { getTemporalProfile } from '@/api/temporal';

export function useTemporal(regionId: string | null) {
  return useQuery({
    queryKey: ['temporal', regionId],
    queryFn: () => getTemporalProfile(regionId!),
    enabled: !!regionId,
    staleTime: 10 * 60 * 1_000,
  });
}
