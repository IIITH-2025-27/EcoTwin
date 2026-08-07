import { apiClient } from './client';
import type { ReportRequest } from '@/types';

export async function generateReportPDF(request: ReportRequest): Promise<Blob> {
  const { data } = await apiClient.post<Blob>(
    `/report/${request.lake_id}`,
    null,
    {
      params: { top_k: request.top_k, method: request.method },
      responseType: 'blob',
      timeout: 180_000,
    },
  );
  return data;
}
