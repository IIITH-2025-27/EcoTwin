import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { createReport, getReport } from '@/api/reports';
import type { Report, ReportRequest } from '@/types';

const POLL_INTERVAL_MS = 3_000;
const MAX_POLL_ATTEMPTS = 40; // 2 minutes

export function useReport() {
  const [report, setReport] = useState<Report | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (reportId: string) => {
      stopPolling();
      pollCountRef.current = 0;

      pollTimerRef.current = setInterval(async () => {
        pollCountRef.current += 1;

        if (pollCountRef.current > MAX_POLL_ATTEMPTS) {
          stopPolling();
          setPollError('Report generation timed out. Please try again.');
          return;
        }

        try {
          const latest = await getReport(reportId);
          setReport(latest);

          if (latest.status === 'completed' || latest.status === 'failed') {
            stopPolling();
          }
        } catch {
          stopPolling();
          setPollError('Failed to fetch report status.');
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  // Cleanup on unmount
  useEffect(() => stopPolling, [stopPolling]);

  const mutation = useMutation({
    mutationFn: (request: ReportRequest) => createReport(request),
    onSuccess: (data) => {
      setReport(data);
      setPollError(null);
      if (data.status === 'pending' || data.status === 'processing') {
        startPolling(data.report_id);
      }
    },
  });

  const reset = useCallback(() => {
    stopPolling();
    setReport(null);
    setPollError(null);
    mutation.reset();
  }, [stopPolling, mutation]);

  return {
    report,
    pollError,
    generate: mutation.mutate,
    isGenerating: mutation.isPending,
    generateError: mutation.error?.message ?? null,
    reset,
  };
}
