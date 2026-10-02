import { apiClient } from './client';
import type { SimilarityMethod, SimilarityResponse } from '@/types';

export async function getAnalogs(
  regionId: string,
  topK: number = 10,
  year?: number,
  method: SimilarityMethod = 'cosine',
): Promise<SimilarityResponse> {
  const params: Record<string, string | number> = {
    top_k: topK,
    method,
  };
  if (year !== undefined) params.year = year;

  const { data } = await apiClient.get<SimilarityResponse>(
    `/similarity/${regionId}`,
    { params, timeout: 120_000 },
  );
  return data;
}
