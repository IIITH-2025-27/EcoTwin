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
  cancelLakeFeatureGeneration,
  generateLakeFeatures,
  getLakeFeatureProgress,
  type GenerateLakeFeaturesResponse,
  type LakeFeatureProgress,
} from '@/api/lakeFeatures';

const POLL_MS = 2000;
const ACTIVE: LakeFeatureProgress['status'][] = ['running', 'cancelling'];

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${Math.round(seconds % 60)}s`;
  return `${Math.round(seconds)}s`;
}

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

  const [starting, setStarting] = useState(false);
  const [progress, setProgress] = useState<LakeFeatureProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // ── Lock scroll ──────────────────────────────────────────────────────────
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) clearTimeout(pollRef.current);
    pollRef.current = null;
  }, []);

  // Chained timeouts so slow responses never overlap
  const poll = useCallback(async () => {
    try {
      const p = await getLakeFeatureProgress();
      if (!mountedRef.current) return;
      setProgress(p);
      if (!ACTIVE.includes(p.status)) {
        stopPolling();
        return;
      }
    } catch {
      // Retry on the next tick
    }
    pollRef.current = setTimeout(poll, POLL_MS);
  }, [stopPolling]);

  const startPolling = useCallback(() => {
    stopPolling();
    void poll();
  }, [poll, stopPolling]);

  // ── Pick up a run already in progress ────────────────────────────────────
  useEffect(() => {
    mountedRef.current = true;
    getLakeFeatureProgress()
      .then((p) => {
        if (!mountedRef.current) return;
        setProgress(p.status === 'idle' ? null : p);
        if (ACTIVE.includes(p.status)) startPolling();
      })
      .catch(() => {});
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [startPolling, stopPolling]);

  // ── Generate handler ─────────────────────────────────────────────────────
  const handleGenerate = async () => {
    setError(null);
    setStarting(true);
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
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    setError(null);
    try {
      await cancelLakeFeatureGeneration();
      // Keep polling: cancelling → cancelled once the current lake-year is saved
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel feature generation.');
    }
  };

  // ── Progress derived values ──────────────────────────────────────────────
  const total      = progress?.total ?? 0;
  const processed  = progress?.processed ?? 0;
  const skippedCnt = progress?.skipped ?? 0;
  const failedCnt  = progress?.failed ?? 0;
  const pct        = total > 0 ? Math.min(100, Math.round((100 * processed) / total)) : 0;
  const isActive   = progress != null && ACTIVE.includes(progress.status);
  const isCancelling = progress?.status === 'cancelling';
  const isDone     = progress?.status === 'done';
  const isFailed   = progress?.status === 'failed';
  const isCancelled = progress?.status === 'cancelled';
  const isRunning  = isActive || starting;

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="lake-features-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget && !starting) onClose(); }}
    >
      <div className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl scrollbar-thin">

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
            disabled={starting}
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
              Processes the merged 30 m Sentinel-2 GeoTIFFs recorded in{' '}
              <code className="text-slate-300">lake_images</code>. Each raster is clipped to the
              lake polygon (lake pixels only, no shore) and the generator computes statistics for
              all 11 spectral bands (B1–B8, B8A, B11, B12, incl. B8 NIR), the clear-observation
              count, 14 spectral indices on surface reflectance, GLCM texture and water metrics,
              stored in <code className="text-slate-300">lake_features</code>.
            </p>
          </div>

          <p className="-mt-2 text-[10px] text-slate-500">
            Without overwrite, lake-years whose current features are newer than their image
            are skipped; older-method rows are always recomputed.
          </p>

          {/* Progress bar */}
          {progress && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  {isCancelling
                    ? 'Cancelling — saving the current lake-year…'
                    : isActive && progress.current_lake_id
                    ? `Processing lake ${progress.current_lake_id}${progress.current_year ? ` (${progress.current_year})` : ''}`
                    : isActive
                    ? 'Preparing…'
                    : isDone
                    ? failedCnt > 0 ? 'Finished with failures' : 'Feature generation complete'
                    : isCancelled
                    ? 'Feature generation cancelled'
                    : isFailed
                    ? 'Feature generation failed'
                    : ''}
                </span>
                <span className="font-mono text-slate-300">
                  {processed} / {total} · {pct}%
                </span>
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-slate-700/60">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500 ease-out',
                    isDone && failedCnt === 0
                      ? 'bg-emerald-500'
                      : isDone
                      ? 'bg-amber-500'
                      : isFailed || isCancelled || isCancelling
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
                {isActive && progress.processing_rate > 0 && (
                  <span className="text-slate-500">
                    ~{formatDuration(progress.estimated_remaining_seconds)} left
                  </span>
                )}
              </div>

              {progress.errors.length > 0 && (
                <div className="max-h-24 overflow-y-auto rounded-lg border border-red-500/30 bg-red-500/5 p-2">
                  {failedCnt > progress.errors.length && (
                    <p className="mb-1 text-[10px] text-red-300">
                      Showing the last {Math.min(5, progress.errors.length)} of {failedCnt} failures
                    </p>
                  )}
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
            disabled={starting}
            className={clsx(
              'rounded-lg px-4 py-2 text-xs transition-colors',
              starting
                ? 'cursor-not-allowed text-slate-600'
                : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-200',
            )}
          >
            Close
          </button>

          {isActive ? (
            <button
              type="button"
              onClick={handleCancel}
              disabled={isCancelling}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/15 px-4 py-2 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/25 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isCancelling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5" />}
              {isCancelling ? 'Cancelling...' : 'Cancel'}
            </button>
          ) : (
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
            {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BarChart3 className="h-3.5 w-3.5" />}
            Generate Features
          </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
