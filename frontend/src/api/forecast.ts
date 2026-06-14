import { apiClient } from './client';
import type { ForecastData } from '@/types';

export async function getForecast(regionId: string): Promise<ForecastData> {
  const { data } = await apiClient.get<ForecastData>(`/forecast/${regionId}`);
  return data;
}
