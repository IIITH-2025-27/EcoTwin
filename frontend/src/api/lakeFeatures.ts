import { apiClient } from './client';

// ── Request / Response types ────────────────────────────────────────────────

export interface GenerateLakeFeaturesRequest {
  year?: number | null;
  overwrite: boolean;
}

export interface GenerateLakeFeaturesResponse {
  status: 'queued' | 'failed';
  message: string;
  total: number;
}

export type LakeFeatureStatus = 'idle' | 'running' | 'cancelling' | 'done' | 'failed' | 'cancelled';

export interface LakeFeatureProgress {
  status: LakeFeatureStatus;
  total: number;
  processed: number;
  skipped: number;
  failed: number;
  current_lake_id: number | null;
  current_year: number | null;
  errors: string[];
  elapsed_seconds: number;
  processing_rate: number;
  estimated_remaining_seconds: number;
}

// ── API calls ───────────────────────────────────────────────────────────────

export async function generateLakeFeatures(
  request: GenerateLakeFeaturesRequest,
): Promise<GenerateLakeFeaturesResponse> {
  const { data } = await apiClient.post<GenerateLakeFeaturesResponse>(
    '/lake-features/generate',
    request,
  );
  return data;
}

export async function getLakeFeatureProgress(): Promise<LakeFeatureProgress> {
  const { data } = await apiClient.get<LakeFeatureProgress>(
    '/lake-features/status',
  );
  return data;
}

export async function cancelLakeFeatureGeneration(): Promise<{ cancelled: boolean }> {
  const { data } = await apiClient.post<{ cancelled: boolean }>('/lake-features/cancel');
  return data;
}
