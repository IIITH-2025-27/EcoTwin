import { apiClient } from './client';

// ── Types ─────────────────────────────────────────────────────────────────

export interface FetchImagesRequest {
  lake_ids: number[] | null;
  years: number[];
  confirmed: true;
}

export interface FetchImagesResponse {
  status: 'queued' | 'failed';
  total_tasks: number;
  message: string;
}

export interface ImageryProgress {
  status: 'idle' | 'running' | 'done' | 'failed' | 'cancelled';
  total: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  current_lake_id: number | null;
  current_year: number | null;
  current_tile_index: string | null;
  errors: string[];
}

// ── API calls ─────────────────────────────────────────────────────────────

export async function startFetchImages(
  request: FetchImagesRequest,
): Promise<FetchImagesResponse> {
  const { data } = await apiClient.post<FetchImagesResponse>(
    '/imagery/fetch',
    request,
  );
  return data;
}

export async function getImageryProgress(): Promise<ImageryProgress> {
  const { data } = await apiClient.get<ImageryProgress>('/imagery/status');
  return data;
}

export async function cancelImageryFetch(): Promise<{ cancelled: boolean }> {
  const { data } = await apiClient.post('/imagery/cancel');
  return data;
}
