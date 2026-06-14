import { apiClient } from './client';
import type { SimilarityResponse } from '@/types';

export async function getAnalogs(
  regionId: string,
  topK: number = 10,
  year?: number,
): Promise<SimilarityResponse> {
  const params: Record<string, string | number> = { top_k: topK };
  if (year !== undefined) params.year = year;

  const { data } = await apiClient.get<SimilarityResponse>(
    `/similarity/${regionId}`,
    { params },
  );
  return data;
}
