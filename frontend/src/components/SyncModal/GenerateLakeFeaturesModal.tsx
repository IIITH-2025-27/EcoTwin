import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  BarChart3,
  Loader2,
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';

import {
  generateLakeFeatures,
  getLakeFeatureProgress,
  type GenerateLakeFeaturesResponse,
  type LakeFeatureProgress,
} from '@/api/lakeFeatures';

interface GenerateLakeFeaturesModalProps {
  onClose: () => void;
}

export default function GenerateLakeFeaturesModal({ onClose }: GenerateLakeFeaturesModalProps) {
  const currentYear = 2025;
  const yearOptions = Array.from({ length: 10 }, (_, i) => currentYear - i);

  const [selectedYear, setSelectedYear] = useState<number | null>(currentYear);
  const [overwrite, setOverwrite] = useState(false);
  const [result, setResult] = useState<GenerateLakeFeaturesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState<LakeFeatureProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Lock scroll ──────────────────────────────────────────────────────────
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // ── Cleanup polling on unmount ───────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const p = await getLakeFeatureProgress();
        setProgress(p);
        if (p.status !== 'running') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setProcessing(false);
        }
      } catch {
        // Keep polling and retry on the next interval.
      }
    }, 2000);
  }, []);

  // ── Generate handler ─────────────────────────────────────────────────────
  const handleGenerate = async () => {
    setError(null);
    setProcessing(true);
    setResult(null);
    setProgress(null);

    try {
      const res = await generateLakeFeatures({
        year: selectedYear,
        overwrite,
      });
      setResult(res);
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start feature generation.');
      setProcessing(false);
    }
  };

  // ── Progress derived values ──────────────────────────────────────────────
  const total      = progress?.total ?? 0;
  const processed  = progress?.processed ?? 0;
  const skippedCnt = progress?.skipped ?? 0;
  const failedCnt  = progress?.failed ?? 0;
  const pct        = total > 0 ? Math.round((100 * processed) / total) : 0;
  const isDone     = progress?.status === 'done';
  const isFailed   = progress?.status === 'failed';
  const isRunning  = progress?.status === 'running' || processing;

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="lake-features-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget && !isRunning) onClose(); }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-600/30 bg-emerald-600/20">
              <BarChart3 className={clsx('h-4 w-4 text-emerald-400', isRunning && 'animate-pulse')} />
            </div>
            <div>
              <h2 id="lake-features-modal-title" className="text-sm font-semibold text-slate-100">
                Generate Lake Features
              </h2>
              <p className="text-xs text-slate-500">
                Extract ecological features from merged Sentinel-2 images
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isRunning}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-700/50 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-5 py-4">
          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              {error}
            </div>
          )}

          {/* Year selector */}
          <div>
            <label className="mb-2 block text-xs font-medium text-slate-300">
              Select year (or process all years)
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => !isRunning && setSelectedYear(null)}
                disabled={isRunning}
                className={clsx(
                  'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                  selectedYear === null
                    ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300 shadow-sm shadow-emerald-500/10'
                    : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                  isRunning && 'cursor-not-allowed opacity-60',
                )}
              >
                All Years
              </button>
              {yearOptions.map((year) => {
                const isSelected = selectedYear === year;
                return (
                  <button
                    key={year}
                    onClick={() => !isRunning && setSelectedYear(year)}
                    disabled={isRunning}
                    className={clsx(
                      'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                      isSelected
                        ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300 shadow-sm shadow-emerald-500/10'
                        : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                      isRunning && 'cursor-not-allowed opacity-60',
                    )}
                  >
                    {year}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Overwrite toggle */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={overwrite}
              onClick={() => !isRunning && setOverwrite((v) => !v)}
              disabled={isRunning}
              className={clsx(
                'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                overwrite ? 'bg-emerald-600' : 'bg-slate-600',
                isRunning && 'cursor-not-allowed opacity-60',
              )}
            >
              <span
                className={clsx(
                  'inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform',
                  overwrite ? 'translate-x-4' : 'translate-x-0.5',
                )}
              />
            </button>
            <span className="text-xs text-slate-300">
              Overwrite existing features
            </span>
          </div>

          {/* Info box */}
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <p className="text-xs leading-relaxed text-slate-400">
              Processes merged Sentinel-2 GeoTIFFs from the <code className="text-slate-300">lake_images</code> table.
              For each lake, clips the raster to the lake polygon, computes 14 spectral indices,
              GLCM texture features, band statistics, water metrics, and stores results
              in <code className="text-slate-300">lake_features</code>.
            </p>
          </div>

          {/* Progress bar */}
          {progress && progress.status !== 'idle' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  {isRunning && progress.current_lake_id
                    ? `Processing lake ${progress.current_lake_id}${progress.current_year ? ` (${progress.current_year})` : ''}`
                    : isDone
                    ? 'Feature generation complete'
                    : isFailed
                    ? 'Feature generation failed'
                    : 'Processing...'}
                </span>
                <span className="font-mono text-slate-300">
                  {processed} / {total}
                </span>
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-slate-700/60">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500 ease-out',
                    isDone
                      ? 'bg-emerald-500'
                      : isFailed
                      ? 'bg-red-500'
                      : 'bg-emerald-500',
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="flex gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {processed - skippedCnt - failedCnt} ok
                </span>
                <span className="flex items-center gap-1 text-amber-400">
                  <AlertTriangle className="h-3 w-3" />
                  {skippedCnt} skipped
                </span>
                <span className="flex items-center gap-1 text-red-400">
                  <XCircle className="h-3 w-3" />
                  {failedCnt} failed
                </span>
              </div>

              {progress.errors.length > 0 && (
                <div className="max-h-24 overflow-y-auto rounded-lg border border-red-500/30 bg-red-500/5 p-2">
                  {progress.errors.slice(-5).map((e, i) => (
                    <p key={i} className="text-[10px] leading-relaxed text-red-400">
                      {e}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {result && !progress && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
              {result.message}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-slate-700/60 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isRunning}
            className={clsx(
              'rounded-lg px-4 py-2 text-xs transition-colors',
              isRunning
                ? 'cursor-not-allowed text-slate-600'
                : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-200',
            )}
          >
            Close
          </button>

          <button
            type="button"
            id="generate-lake-features-btn"
            onClick={handleGenerate}
            disabled={isRunning}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              isRunning
                ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                : 'bg-emerald-600 text-white hover:bg-emerald-500',
            )}
          >
            {processing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BarChart3 className="h-3.5 w-3.5" />}
            {processing ? 'Generating...' : 'Generate Features'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
