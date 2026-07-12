import { useQuery } from '@tanstack/react-query';

import { listRegions } from '@/api/regions';

export function useRegions(country = 'India') {
  return useQuery({
    queryKey: ['regions', country],
    queryFn: () => listRegions(country),
    staleTime: 30_000,
  });
}
