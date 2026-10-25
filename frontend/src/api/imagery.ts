import { apiClient } from './client';

// ── Types ─────────────────────────────────────────────────────────────────

export interface FetchImagesRequest {
  lake_ids: number[] | null;
  years: number[];
  confirmed: true;
  /** Absolute directory for every requested year; null = each year's current folder. */
  data_root?: string | null;
  /** Per-year directories; override data_root. Recorded via lake_images / lake_tiles paths. */
  year_roots?: Record<number, string> | null;
}

export interface FetchImagesResponse {
  status: 'queued' | 'failed';
  total_tasks: number;
  message: string;
}

/** Lake-year counters (total/processed/success/failed/skipped) drive the
 *  progress bar; tile counters are extra detail. */
export interface ImageryProgress {
  status: 'idle' | 'running' | 'cancelling' | 'done' | 'failed' | 'cancelled';
  total: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  tiles_completed: number;
  tiles_failed: number;
  active_lakes: number;
  current_lake_id: number | null;
  current_year: number | null;
  current_tile_index: string | null;
  /** Storage root per year of this run. */
  year_roots: Record<string, string>;
  errors: string[];
}

export interface StorageLocation {
  path: string;
  label: string;
  free_bytes: number;
  total_bytes: number;
}

export interface YearRootUsage {
  root: string;
  lakes: number;
  free_bytes: number | null;
  total_bytes: number | null;
}

/** Where a year's images are, read from the paths in lake_images. */
export interface YearStorage {
  year: number;
  /** Folder new downloads of this year go to unless changed (SENTINEL_DATA_DIR). */
  data_root: string;
  /** True when the year has no images yet (SENTINEL_DATA_DIR). */
  is_default: boolean;
  free_bytes: number | null;
  total_bytes: number | null;
  roots: YearRootUsage[];
}

export interface StorageInfo {
  default_root: string;
  years: YearStorage[];
  active_lakes: number;
  /** Upper bound for one year of merged images (tiles need about as much again). */
  estimated_bytes_per_year: number;
  suggestions: StorageLocation[];
}

export interface StorageCheck {
  path: string;
  valid: boolean;
  error: string | null;
  free_bytes: number | null;
  total_bytes: number | null;
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

export async function getImageryStorage(): Promise<StorageInfo> {
  const { data } = await apiClient.get<StorageInfo>('/imagery/storage');
  return data;
}

export async function checkImageryStorage(path: string): Promise<StorageCheck> {
  const { data } = await apiClient.post<StorageCheck>('/imagery/storage/check', { path });
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
