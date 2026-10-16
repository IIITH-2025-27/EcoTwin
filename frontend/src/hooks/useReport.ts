import { useCallback, useEffect, useState } from 'react';
import { create } from 'zustand';
import { generateReportPDF, type ReportFile } from '@/api/reports';
import { useMapStore } from '@/store/mapStore';
import type { ReportRequest } from '@/types';

export const REPORT_STEPS = [
  'Collecting Lake Information',
  'Building Similarity Analysis',
  'Preparing Maps',
  'Rendering Report',
  'Creating PDF',
] as const;

const STEP_INTERVAL_MS = 2_400;

// ── Report run state ─────────────────────────────────────────────────────
// Lives outside React so a generation in progress survives the Report panel
// unmounting (tab switch). It is abandoned only when a different lake is selected.
interface ReportRunState {
  lakeId: number | null;
  status: 'idle' | 'generating' | 'success' | 'error';
  error: string | null;
  startedAt: number | null;
  // Bumped on every new run / reset so a superseded request can't write back.
  runId: number;
}

const IDLE = { status: 'idle', error: null, startedAt: null } as const;

const useReportStore = create<ReportRunState>(() => ({
  lakeId: null,
  ...IDLE,
  runId: 0,
}));

function openReport({ blob, filename }: ReportFile) {
  const url = URL.createObjectURL(blob);
  const newTab = window.open(url, '_blank');
  if (!newTab) {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

async function startReport(request: ReportRequest) {
  const runId = useReportStore.getState().runId + 1;
  useReportStore.setState({
    lakeId: request.lake_id,
    status: 'generating',
    error: null,
    startedAt: Date.now(),
    runId,
  });

  try {
    const file = await generateReportPDF(request);
    if (useReportStore.getState().runId !== runId) return;
    openReport(file);
    useReportStore.setState({ status: 'success' });
  } catch (error) {
    if (useReportStore.getState().runId !== runId) return;
    useReportStore.setState({
      status: 'error',
      error: error instanceof Error ? error.message : 'Report generation failed',
    });
  }
}

function resetReport(lakeId: number | null = useReportStore.getState().lakeId) {
  useReportStore.setState((s) => ({ lakeId, ...IDLE, runId: s.runId + 1 }));
}

// Selecting a different lake abandons the previous run. Transient `null`
// selections (the map clears before re-selecting) don't count as a new lake.
useMapStore.subscribe((state) => {
  const lakeId = state.selectedLake?.lake_id ?? null;
  if (lakeId !== null && lakeId !== useReportStore.getState().lakeId) {
    resetReport(lakeId);
  }
});

export function useReport() {
  const { status, error, startedAt } = useReportStore();
  const isGenerating = status === 'generating';

  // Tick while generating so the checklist follows real elapsed time.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!isGenerating) return;
    setNow(Date.now());
    const interval = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(interval);
  }, [isGenerating]);

  const stepIndex =
    isGenerating && startedAt !== null
      ? Math.min(Math.floor((now - startedAt) / STEP_INTERVAL_MS), REPORT_STEPS.length - 1)
      : 0;

  const reset = useCallback(() => resetReport(), []);

  return {
    steps: REPORT_STEPS,
    stepIndex,
    generate: startReport,
    isGenerating,
    isSuccess: status === 'success',
    error,
    reset,
  };
}
