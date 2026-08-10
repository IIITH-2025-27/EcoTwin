import { apiClient } from './client';

// ── Request / Response types ────────────────────────────────────────────────

export interface GenerateB8FeaturesRequest {
  year?: number | null;
  overwrite: boolean;
}

export interface GenerateB8FeaturesResponse {
  status: 'queued' | 'failed';
  message: string;
  total: number;
}

export type B8FeatureStatus = 'idle' | 'running' | 'done' | 'failed';

export interface B8FeatureProgress {
  status: B8FeatureStatus;
  total: number;
  processed: number;
  skipped: number;
  failed: number;
  current_lake_id: number | null;
  current_year: number | null;
  errors: string[];
}

// ── API calls ───────────────────────────────────────────────────────────────

export async function generateB8Features(
  request: GenerateB8FeaturesRequest,
): Promise<GenerateB8FeaturesResponse> {
  const { data } = await apiClient.post<GenerateB8FeaturesResponse>(
    '/lake-features/generate-b8',
    request,
  );
  return data;
}

export async function getB8FeatureProgress(): Promise<B8FeatureProgress> {
  const { data } = await apiClient.get<B8FeatureProgress>(
    '/lake-features/status-b8',
  );
  return data;
}
