import { useQuery } from '@tanstack/react-query';
import { fetchSyncedStates } from '@/api/regions';

/**
 * Returns the list of Indian state names (matching INDIA_STATE_CENTROIDS keys)
 * that have at least one region with ML pipeline data in the database.
 * Refreshes every 30 s so the map updates after a sync completes.
 */
export function useSyncedStates() {
  return useQuery({
    queryKey: ['syncedStates'],
    queryFn: fetchSyncedStates,
    refetchInterval: 30_000,
    staleTime: 10_000,
    initialData: [] as string[],
  });
}
