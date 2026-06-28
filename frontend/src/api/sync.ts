import { apiClient } from './client';

// ── Types (mirrored from backend schemas/sync.py) ─────────────────────────

export interface IndiaState {
  name: string;
  lat: number;
  lon: number;
}

export interface StatesResponse {
  states: IndiaState[];
  max_selection: number;
  year_start: number;
  year_end: number;
}

export type SyncMode = 'wipe' | 'backup';

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
  states: string[];
  duration: SyncDuration;
  sync_mode: SyncMode;
  confirmed: true;
}

export interface SyncJobResponse {
  job_id: string;
  status: 'queued' | 'failed';
  states: string[];
  years: number[];
  sync_mode: SyncMode;
  tasks_dispatched: number;
  message: string;
  backup_path: string | null;
}

// ── Status polling types ───────────────────────────────────────────────────

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed';
export type OverallStatus = 'pending' | 'running' | 'success' | 'failed' | 'partial';

export interface TaskItem {
  task_id: string;
  state: string;    // Indian state name
  year: number;
  status: TaskStatus;
  error: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  states: string[];
  years: number[];
  overall: OverallStatus;
  total: number;
  counts: {
    pending: number;
    running: number;
    success: number;
    failed: number;
  };
  tasks: TaskItem[];
}

// ── API calls ─────────────────────────────────────────────────────────────

export async function fetchStates(): Promise<StatesResponse> {
  const { data } = await apiClient.get<StatesResponse>('/sync/states');
  return data;
}

export async function startSync(request: SyncRequest): Promise<SyncJobResponse> {
  const { data } = await apiClient.post<SyncJobResponse>('/sync/start', request);
  return data;
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const { data } = await apiClient.get<JobStatusResponse>(`/sync/status/${jobId}`);
  return data;
}
