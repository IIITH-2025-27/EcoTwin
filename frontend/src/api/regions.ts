import { apiClient } from './client';
import type { RegionQueryRequest, RegionQueryResult, RegionSummary } from '@/types';

export async function getRegion(regionId: string): Promise<RegionSummary> {
  const { data } = await apiClient.get<RegionSummary>(`/regions/${regionId}`);
  return data;
}

export async function queryRegionByCoords(
  lat: number,
  lon: number,
): Promise<RegionQueryResult> {
  const { data } = await apiClient.post<RegionQueryResult>('/regions/query', {
    lat,
    lon,
  } satisfies RegionQueryRequest);
  return data;
}

/** Returns state names (matching INDIA_STATE_CENTROIDS keys) that have pipeline data. */
export async function fetchSyncedStates(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/regions/synced-states');
  return data;
}
