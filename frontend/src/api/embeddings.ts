import { apiClient } from './client';

export interface GenerateEmbeddingsRequest {
  lake_ids: number[] | null;
  years: number[];
  confirmed: true;
}

export interface GenerateEmbeddingsResponse {
  status: 'queued' | 'failed';
  total_tasks: number;
  message: string;
}

export interface MergeEmbeddingsRequest {
  years: number[];
  country: string;
  confirmed: true;
}

export interface MergeEmbeddingsResponse {
  status: 'queued' | 'failed';
  total_tasks: number;
  message: string;
}

export type EmbeddingStatus = 'idle' | 'running' | 'done' | 'failed' | 'cancelled';

export interface EmbeddingProgressResponse {
  status: EmbeddingStatus;
  total: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  current_lake_id: number | null;
  current_year: number | null;
  current_step: string | null;
  errors: string[];
}

export interface AvailableEmbeddingYearsResponse {
  years: number[];
}

export async function startEmbeddingGeneration(
  request: GenerateEmbeddingsRequest,
): Promise<GenerateEmbeddingsResponse> {
  const { data } = await apiClient.post<GenerateEmbeddingsResponse>('/embeddings/generate', request);
  return data;
}

export async function getEmbeddingProgress(): Promise<EmbeddingProgressResponse> {
  const { data } = await apiClient.get<EmbeddingProgressResponse>('/embeddings/status');
  return data;
}

export async function getAvailableEmbeddingYears(): Promise<number[]> {
  const { data } = await apiClient.get<AvailableEmbeddingYearsResponse>('/embeddings/merge/options', {
  });
  return data.years;
}

export async function mergeEmbeddings(request: MergeEmbeddingsRequest): Promise<MergeEmbeddingsResponse> {
  const { data } = await apiClient.post<MergeEmbeddingsResponse>('/embeddings/merge', request);
  return data;
}

export async function cancelEmbeddingGeneration(): Promise<{ cancelled: boolean }> {
  const { data } = await apiClient.post<{ cancelled: boolean }>('/embeddings/cancel');
  return data;
}
