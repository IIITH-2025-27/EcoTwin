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

// ── Merge types ───────────────────────────────────────────────────────────

export interface MergeTilesRequest {
  years: number[];
  delete_tiles: boolean;
}

export interface MergeTilesResponse {
  status: 'queued' | 'failed';
  message: string;
}

export interface MergeProgress {
  status: 'idle' | 'running' | 'done' | 'failed';
  total: number;
  processed: number;
  success: number;
  failed: number;
  current_lake_id: number | null;
  current_year: number | null;
  errors: string[];
}

export interface MergeYearOption {
  year: number;
  lake_count: number;
  output_path_pattern: string;
}

export interface MergeOptionsResponse {
  years: MergeYearOption[];
  data_root: string;
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

// ── Merge API calls ───────────────────────────────────────────────────────

export async function getMergeOptions(): Promise<MergeOptionsResponse> {
  const { data } = await apiClient.get<MergeOptionsResponse>(
    '/imagery/merge/options',
  );
  return data;
}

export async function startMergeTiles(
  request: MergeTilesRequest,
): Promise<MergeTilesResponse> {
  const { data } = await apiClient.post<MergeTilesResponse>(
    '/imagery/merge',
    request,
  );
  return data;
}

export async function getMergeProgress(): Promise<MergeProgress> {
  const { data } = await apiClient.get<MergeProgress>(
    '/imagery/merge/status',
  );
  return data;
}
