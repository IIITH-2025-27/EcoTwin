import { apiClient } from './client';

export interface GenerateEmbeddingsRequest {
  lake_ids: number[] | null;
  years: number[];
  /** Lake share of the combined embedding; null = weight already in use. */
  lake_weight?: number | null;
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
  /** w in normalize(w·lake + (1−w)·shore), 0–1. */
  lake_weight: number;
  confirmed: true;
}

export interface MergeEmbeddingsResponse {
  status: 'queued' | 'failed';
  total_tasks: number;
  message: string;
}

export type MergeEmbeddingStatus = 'idle' | 'running' | 'done' | 'failed';

export interface MergeEmbeddingProgress {
  status: MergeEmbeddingStatus;
  total: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  current_lake_id: number | null;
  current_year: number | null;
  lake_weight: number | null;
  errors: string[];
}

export type EmbeddingStatus = 'idle' | 'running' | 'cancelling' | 'done' | 'failed' | 'cancelled';

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
  /** Lake weight the run blends with. */
  lake_weight: number | null;
  errors: string[];
}

export interface LakeWeightCount {
  lake_weight: number;
  lakes: number;
}

export interface EmbeddingYearInfo {
  year: number;
  lakes: number;
  weights: LakeWeightCount[];
}

export interface EmbeddingMergeOptions {
  years: number[];
  year_details: EmbeddingYearInfo[];
  /** Weight most stored embeddings use (new embeddings use it too). */
  current_lake_weight: number | null;
  /** EMBEDDING_LAKE_WEIGHT setting. */
  default_lake_weight: number;
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

export async function getEmbeddingMergeOptions(): Promise<EmbeddingMergeOptions> {
  const { data } = await apiClient.get<EmbeddingMergeOptions>('/embeddings/merge/options');
  return data;
}

export async function mergeEmbeddings(request: MergeEmbeddingsRequest): Promise<MergeEmbeddingsResponse> {
  const { data } = await apiClient.post<MergeEmbeddingsResponse>('/embeddings/merge', request);
  return data;
}

export async function getMergeEmbeddingProgress(): Promise<MergeEmbeddingProgress> {
  const { data } = await apiClient.get<MergeEmbeddingProgress>('/embeddings/merge/status');
  return data;
}

export async function cancelEmbeddingGeneration(): Promise<{ cancelled: boolean }> {
  const { data } = await apiClient.post<{ cancelled: boolean }>('/embeddings/cancel');
  return data;
}
