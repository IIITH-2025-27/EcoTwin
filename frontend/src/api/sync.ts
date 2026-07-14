import { apiClient } from './client';

// ── Types (mirrored from backend schemas/sync.py) ─────────────────────────

export interface SyncCountryResponse {
  country: string;
  year_start: number;
  year_end: number;
  max_year_range: number;
}

export type SyncSource = 'hydrolakes' | 'stored_regions';

export type SyncMode = 'refresh' | 'backup';

export interface SyncDurationYear {
  mode: 'year';
  year: number;
}

export interface SyncDurationRange {
  mode: 'duration';
  start_year: number;
  start_month: number;
  end_year: number;
  end_month: number;
}

export type SyncDuration = SyncDurationYear | SyncDurationRange;

export interface SyncRequest {
  source_type: SyncSource;
  country: string;
  region_ids?: string[];
  states?: string[];
  duration: SyncDuration;
  sync_mode: SyncMode;
  confirmed: true;
}

export interface SyncJobResponse {
  job_id: string;
  status: 'queued' | 'failed' | 'completed' | 'cancelled';
  source_type: SyncSource;
  country: string;
  region_ids: string[];
  years: number[];
  sync_mode: SyncMode;
  tasks_dispatched: number;
  total_regions: number;
  inserted_regions: number;
  updated_regions: number;
  skipped_regions: number;
  message: string;
  backup_path: string | null;
}

// ── Global progress response (from GET /sync/status) ─────────────────────

export type SyncStatus = 'idle' | 'running' | 'done' | 'failed' | 'cancelled';

export interface SyncProgressResponse {
  status: SyncStatus;
  total_lakes: number;
  processed: number;
  success: number;
  failed: number;
  current_lake: string | null;
  current_year: number | null;
  errors: string[];
}

export interface HydroLakeBoundary {
  hydrolake_id: string;
  name: string;
  country: string;
  center_lat: number;
  center_lon: number;
  area_sqkm: number;
  bbox: number[] | null;
  geometry: GeoJSON.Geometry | null;
}

export interface LakeImportResponse {
  source_path: string;
  country: string;
  total_records: number;
  inserted_records: number;
  updated_records: number;
  skipped_records: number;
  message: string;
}

// ── API calls ─────────────────────────────────────────────────────────────

export async function fetchSyncCountry(): Promise<SyncCountryResponse> {
  const { data } = await apiClient.get<SyncCountryResponse>('/sync/country');
  return data;
}

export async function fetchHydrolakeBoundaries(
  country = 'India',
): Promise<HydroLakeBoundary[]> {
  const { data } = await apiClient.get<HydroLakeBoundary[]>('/sync/hydrolakes/boundaries', {
    params: { country },
  });
  return data;
}

export async function importLakesTable(country = 'India'): Promise<LakeImportResponse> {
  const { data } = await apiClient.post<LakeImportResponse>('/sync/lakes/import', null, {
    params: { country },
    timeout: 300_000,
  });
  return data;
}

export async function startSync(request: SyncRequest): Promise<SyncJobResponse> {
  const { data } = await apiClient.post<SyncJobResponse>('/sync/start', request);
  return data;
}

export async function cancelSync(jobId?: string): Promise<{ job_id: string | null; cancelled: boolean; active_jobs?: number }> {
  const { data } = await apiClient.post('/sync/cancel', null, {
    params: jobId ? { job_id: jobId } : {},
  });
  return data;
}

/** Poll current/last sync progress — no job ID needed. */
export async function getSyncProgress(): Promise<SyncProgressResponse> {
  const { data } = await apiClient.get<SyncProgressResponse>('/sync/status');
  return data;
}

export async function fetchLakeStates(country = 'India'): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/lakes/states', { params: { country } });
  return data;
}
