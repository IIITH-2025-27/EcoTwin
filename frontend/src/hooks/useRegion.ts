import { useQuery } from '@tanstack/react-query';
import { getRegion } from '@/api/regions';

export function useRegion(regionId: string | null) {
  return useQuery({
    queryKey: ['region', regionId],
    queryFn: () => getRegion(regionId!),
    enabled: !!regionId,
  });
}
