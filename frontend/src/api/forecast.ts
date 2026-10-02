import { apiClient } from './client';
import type { ForecastData, EcologicalForecastData, SimilarityMethod } from '@/types';

export async function getForecast(
  regionId: string,
  method: SimilarityMethod = 'cosine',
): Promise<ForecastData> {
  const { data } = await apiClient.get<ForecastData>(`/forecast/${regionId}`, {
    params: { method },
    timeout: 120_000,
  });
  return data;
}

export async function getEcologicalForecast(
  regionId: string,
  method: SimilarityMethod = 'cosine',
  numAnalogs: number = 5,
): Promise<EcologicalForecastData> {
  const { data } = await apiClient.get<EcologicalForecastData>(
    `/forecast/ecological/${regionId}`,
    { params: { method, num_analogs: numAnalogs }, timeout: 120_000 },
  );
  return data;
}
