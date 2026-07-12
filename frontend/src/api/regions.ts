import { apiClient } from './client';
import type {
  LakeGeometry,
  LakeRegionResponse,
  LakeSearchResult,
  RegionQueryRequest,
  RegionQueryResult,
  RegionSummary,
} from '@/types';

export interface LakeCountResponse {
  country: string;
  total_lakes: number;
}

/** Lightweight marker data — centroid only, no geometry. */
export interface LakeMarker {
  lake_id: number;
  display_name: string;
  state: string | null;
  area_sqkm: number | null;
  center_lat: number;
  center_lon: number;
}

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

export async function listRegions(country = 'India'): Promise<LakeRegionResponse[]> {
  const { data } = await apiClient.get<LakeRegionResponse[]>('/regions', {
    params: { country },
  });
  return data;
}

export async function getLakeCount(country = 'India'): Promise<LakeCountResponse> {
  const { data } = await apiClient.get<LakeCountResponse>('/lakes/count', {
    params: { country },
  });
  return data;
}

export async function searchLakes(query: string): Promise<LakeSearchResult[]> {
  const { data } = await apiClient.get<LakeSearchResult[]>('/lakes/search', {
    params: { query },
  });
  return data;
}

export async function getLakeGeometry(lakeId: number): Promise<LakeGeometry> {
  const { data } = await apiClient.get<LakeGeometry>(`/lakes/${lakeId}`);
  return data;
}

/** Return centroid markers for all active lakes (no geometry payload). */
export async function getActiveLakeMarkers(country = 'India'): Promise<LakeMarker[]> {
  const { data } = await apiClient.get<LakeMarker[]>('/lakes/markers', {
    params: { country },
  });
  return data;
}
