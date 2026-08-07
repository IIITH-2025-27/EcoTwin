import { useCallback, useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { generateReportPDF } from '@/api/reports';
import type { ReportRequest } from '@/types';

export const REPORT_STEPS = [
  'Collecting Lake Information',
  'Building Similarity Analysis',
  'Preparing Maps',
  'Rendering Report',
  'Creating PDF',
] as const;

const STEP_INTERVAL_MS = 2_400;

export function useReport() {
  const [stepIndex, setStepIndex] = useState(0);

  const mutation = useMutation({
    mutationFn: (request: ReportRequest) => generateReportPDF(request),
    onSuccess: (pdfBlob) => {
      const url = URL.createObjectURL(pdfBlob);
      const newTab = window.open(url, '_blank');
      if (!newTab) {
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'ecotwin-report.pdf';
        anchor.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    },
  });

  // Advance the step checklist while the PDF is being generated.
  useEffect(() => {
    if (!mutation.isPending) return;
    setStepIndex(0);
    const interval = setInterval(() => {
      setStepIndex((index) => Math.min(index + 1, REPORT_STEPS.length - 1));
    }, STEP_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [mutation.isPending]);

  const reset = useCallback(() => {
    setStepIndex(0);
    mutation.reset();
  }, [mutation]);

  return {
    steps: REPORT_STEPS,
    stepIndex,
    generate: mutation.mutate,
    isGenerating: mutation.isPending,
    isSuccess: mutation.isSuccess,
    error: mutation.error?.message ?? null,
    reset,
  };
}
