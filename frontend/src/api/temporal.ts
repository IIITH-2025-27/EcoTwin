import { apiClient } from './client';
import type { TemporalData } from '@/types';

export async function getTemporalProfile(regionId: string): Promise<TemporalData> {
  const { data } = await apiClient.get<TemporalData>(`/temporal/${regionId}`);
  return data;
}
