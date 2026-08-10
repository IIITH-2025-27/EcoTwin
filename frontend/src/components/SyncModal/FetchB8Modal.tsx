import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Radar,
  Loader2,
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';

import {
  generateB8Features,
  getB8FeatureProgress,
  type GenerateB8FeaturesResponse,
  type B8FeatureProgress,
} from '@/api/b8Features';

const YEAR_OPTIONS = Array.from({ length: 10 }, (_, i) => 2025 - i); // 2025..2016

interface FetchB8ModalProps {
  onClose: () => void;
}

export default function FetchB8Modal({ onClose }: FetchB8ModalProps) {
  const [selectedYear, setSelectedYear] = useState<number | null>(2025);
  const [overwrite, setOverwrite] = useState(false);
  const [result, setResult] = useState<GenerateB8FeaturesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState<B8FeatureProgress | null>(null);
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
        const p = await getB8FeatureProgress();
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
      const res = await generateB8Features({
        year: selectedYear,
        overwrite,
      });
      setResult(res);
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start B8 feature generation.');
      setProcessing(false);
    }
  };

  // ── Progress derived values ──────────────────────────────────────────────
  const total      = progress?.total ?? 0;
  const okCnt      = progress?.processed ?? 0;
  const skippedCnt = progress?.skipped ?? 0;
  const failedCnt  = progress?.failed ?? 0;
  // "processed" from the API means "successfully completed" — it does not
  // include skipped/failed lake-years, so the bar must sum all three to
  // reflect how much of the batch has actually been resolved either way.
  const settled    = okCnt + skippedCnt + failedCnt;
  const pct        = total > 0 ? Math.round((100 * settled) / total) : 0;
  const isDone     = progress?.status === 'done';
  const isFailed   = progress?.status === 'failed';
  const isRunning  = progress?.status === 'running' || processing;

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fetch-b8-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget && !isRunning) onClose(); }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-indigo-600/30 bg-indigo-600/20">
              <Radar className={clsx('h-4 w-4 text-indigo-400', isRunning && 'animate-pulse')} />
            </div>
            <div>
              <h2 id="fetch-b8-modal-title" className="text-sm font-semibold text-slate-100">
                Fetch B8 (NIR) Band
              </h2>
              <p className="text-xs text-slate-500">
                Fetch Sentinel-2 B8 and compute zonal statistics, year by year
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
                    ? 'border-indigo-500/50 bg-indigo-500/20 text-indigo-300 shadow-sm shadow-indigo-500/10'
                    : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                  isRunning && 'cursor-not-allowed opacity-60',
                )}
              >
                All Years
              </button>
              {YEAR_OPTIONS.map((year) => {
                const isSelected = selectedYear === year;
                return (
                  <button
                    key={year}
                    onClick={() => !isRunning && setSelectedYear(year)}
                    disabled={isRunning}
                    className={clsx(
                      'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                      isSelected
                        ? 'border-indigo-500/50 bg-indigo-500/20 text-indigo-300 shadow-sm shadow-indigo-500/10'
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
                overwrite ? 'bg-indigo-600' : 'bg-slate-600',
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
              Re-fetch lakes already marked completed
            </span>
          </div>

          {/* Info box */}
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <p className="text-xs leading-relaxed text-slate-400">
              For each active lake with a completed <code className="text-slate-300">lake_features</code> row
              for the selected year, fetches a dedicated Sentinel-2 B8 composite, clips it to the lake
              polygon, and stores <code className="text-slate-300">b8_mean/std/min/max/median</code> plus a
              per-lake-year <code className="text-slate-300">b8_status</code>. Independent of the main
              B2-B7 pipeline — does not affect embeddings.
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
                    ? `B8 fetch complete — ${okCnt} ok, ${skippedCnt} skipped, ${failedCnt} failed`
                    : isFailed
                    ? 'B8 fetch failed'
                    : 'Processing...'}
                </span>
                <span className="font-mono text-slate-300">
                  {settled} / {total}
                </span>
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-slate-700/60">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500 ease-out',
                    isFailed ? 'bg-red-500' : 'bg-indigo-500',
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="flex gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {okCnt} completed
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
            <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-3 text-xs text-indigo-300">
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
            id="fetch-b8-btn"
            onClick={handleGenerate}
            disabled={isRunning}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              isRunning
                ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                : 'bg-indigo-600 text-white hover:bg-indigo-500',
            )}
          >
            {processing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Radar className="h-3.5 w-3.5" />}
            {processing ? 'Fetching...' : 'Fetch B8'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
