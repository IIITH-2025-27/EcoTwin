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

export type LakeFeatureStatus = 'idle' | 'running' | 'done' | 'failed';

export interface LakeFeatureProgress {
  status: LakeFeatureStatus;
  total: number;
  processed: number;
  skipped: number;
  failed: number;
  current_lake_id: number | null;
  current_year: number | null;
  errors: string[];
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
