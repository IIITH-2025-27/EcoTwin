import { apiClient } from './client';
import type { Report, ReportRequest } from '@/types';

export async function createReport(request: ReportRequest): Promise<Report> {
  const { data } = await apiClient.post<Report>('/report', request);
  return data;
}

export async function getReport(reportId: string): Promise<Report> {
  const { data } = await apiClient.get<Report>(`/report/${reportId}`);
  return data;
}
