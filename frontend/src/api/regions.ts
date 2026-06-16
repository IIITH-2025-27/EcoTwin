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
