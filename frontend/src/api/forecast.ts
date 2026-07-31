import { apiClient } from './client';
import type { ForecastData, SimilarityMethod } from '@/types';

export async function getForecast(
  regionId: string,
  method: SimilarityMethod = 'cosine',
): Promise<ForecastData> {
  const { data } = await apiClient.get<ForecastData>(`/forecast/${regionId}`, {
    params: { method },
  });
  return data;
}
