import { apiClient } from './client';
import type { ReportRequest } from '@/types';

export interface ReportFile {
  blob: Blob;
  filename: string;
}

function parseFilename(contentDisposition: string | undefined): string | null {
  if (!contentDisposition) return null;
  const match = /filename="([^"]+)"/.exec(contentDisposition);
  return match ? match[1] : null;
}

export async function generateReportPDF(request: ReportRequest): Promise<ReportFile> {
  const { data, headers } = await apiClient.post<Blob>(
    `/report/${request.lake_id}`,
    null,
    {
      params: { top_k: request.top_k, method: request.method },
      responseType: 'blob',
      timeout: 180_000,
    },
  );
  const filename =
    parseFilename(headers['content-disposition']) ?? `ecotwin-report.pdf`;
  return { blob: data, filename };
}
