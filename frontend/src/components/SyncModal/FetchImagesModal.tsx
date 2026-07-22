import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Image, Loader2, X, XCircle, CheckCircle2, AlertTriangle, Satellite } from 'lucide-react';
import { clsx } from 'clsx';

import {
  startFetchImages,
  getImageryProgress,
  cancelImageryFetch,
  type FetchImagesResponse,
  type ImageryProgress,
} from '@/api/imagery';

interface FetchImagesModalProps {
  onClose: () => void;
}

const CURRENT_YEAR = 2025;
const YEAR_OPTIONS = Array.from({ length: 10 }, (_, i) => CURRENT_YEAR - i);

export default function FetchImagesModal({ onClose }: FetchImagesModalProps) {
  const [selectedYears, setSelectedYears] = useState<number[]>([CURRENT_YEAR - 1]);
  const [fetching, setFetching] = useState(false);
  const [result, setResult] = useState<FetchImagesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ImageryProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Prevent body scroll when modal is open
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const p = await getImageryProgress();
        setProgress(p);
        if (p.status !== 'running') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setFetching(false);
        }
      } catch {
        // Silently retry
      }
    }, 2000);
  }, []);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year) ? prev.filter((y) => y !== year) : [...prev, year].sort((a, b) => a - b),
    );
  };

  const handleFetch = async () => {
    if (selectedYears.length === 0) {
      setError('Please select at least one year.');
      return;
    }

    setFetching(true);
    setError(null);
    setResult(null);
    setProgress(null);

    try {
      const res = await startFetchImages({
        lake_ids: null, // all active lakes
        years: selectedYears,
        confirmed: true,
      });
      setResult(res);
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start image download.');
      setFetching(false);
    }
  };

  const handleCancel = async () => {
    try {
      await cancelImageryFetch();
      setError('Download cancelled by user.');
      setFetching(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel.');
    }
  };

  const progressPercent =
    progress && progress.total > 0
      ? Math.round((progress.processed / progress.total) * 100)
      : 0;

  const isRunning = progress?.status === 'running' || fetching;
  const isDone = progress?.status === 'done';
  const isFailed = progress?.status === 'failed';
  const isCancelled = progress?.status === 'cancelled';

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fetch-images-title"
      onClick={(event) => {
        if (event.target === event.currentTarget && !isRunning) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/15">
              <Satellite className="h-4 w-4 text-cyan-400" />
            </div>
            <div>
              <h2
                id="fetch-images-title"
                className="text-sm font-semibold text-slate-100"
              >
                Fetch Satellite Images
              </h2>
              <p className="text-xs text-slate-500">
                Download Sentinel-2 composites for all active lakes
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isRunning}
            className={clsx(
              'rounded-lg p-1.5 transition-colors',
              isRunning
                ? 'cursor-not-allowed text-slate-600'
                : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-200',
            )}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Body ────────────────────────────────────────────────── */}
        <div className="space-y-4 px-5 py-4">
          {/* Year selector */}
          <div>
            <label className="mb-2 block text-xs font-medium text-slate-300">
              Select years to download
            </label>
            <div className="flex flex-wrap gap-2">
              {YEAR_OPTIONS.map((year) => {
                const isSelected = selectedYears.includes(year);
                return (
                  <button
                    key={year}
                    onClick={() => !isRunning && toggleYear(year)}
                    disabled={isRunning}
                    className={clsx(
                      'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                      isSelected
                        ? 'border-cyan-500/50 bg-cyan-500/20 text-cyan-300 shadow-sm shadow-cyan-500/10'
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

          {/* Info box */}
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <p className="text-xs leading-relaxed text-slate-400">
              This downloads Sentinel-2 Surface Reflectance yearly median
              composites (Bands B2–B7) for each active lake. The pipeline
              buffers each lake polygon by 2 km, partitions the region into
              10 km × 10 km tiles, and downloads each tile from Google Earth
              Engine with cloud masking applied.
            </p>
            <p className="mt-1.5 text-xs text-slate-500">
              Already downloaded tiles will be skipped automatically.
            </p>
          </div>

          {/* Progress bar */}
          {progress && progress.status !== 'idle' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  {isRunning && progress.current_lake_id
                    ? `Processing lake ${progress.current_lake_id} / ${progress.current_year}${progress.current_tile_index ? ` — tile ${progress.current_tile_index}` : ''}`
                    : isDone
                    ? 'Download complete'
                    : isCancelled
                    ? 'Download cancelled'
                    : isFailed
                    ? 'Download failed'
                    : 'Processing…'}
                </span>
                <span className="font-mono text-slate-300">
                  {progress.processed} / {progress.total}
                </span>
              </div>

              {/* Bar */}
              <div className="h-2 overflow-hidden rounded-full bg-slate-700/60">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500 ease-out',
                    isDone
                      ? 'bg-emerald-500'
                      : isFailed || isCancelled
                      ? 'bg-red-500'
                      : 'bg-cyan-500',
                  )}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              {/* Stats chips */}
              <div className="flex gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {progress.success} ok
                </span>
                <span className="flex items-center gap-1 text-amber-400">
                  <AlertTriangle className="h-3 w-3" />
                  {progress.skipped} skipped
                </span>
                <span className="flex items-center gap-1 text-red-400">
                  <XCircle className="h-3 w-3" />
                  {progress.failed} failed
                </span>
              </div>

              {/* Error list */}
              {progress.errors.length > 0 && (
                <div className="max-h-24 overflow-y-auto rounded-lg border border-red-500/30 bg-red-500/5 p-2 scrollbar-thin">
                  {progress.errors.slice(-5).map((e, i) => (
                    <p key={i} className="text-[10px] leading-relaxed text-red-400">
                      {e}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Status messages */}
          {result && !progress && (
            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3 text-xs text-cyan-300">
              {result.message}
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              {error}
            </div>
          )}
        </div>

        {/* ── Footer ──────────────────────────────────────────────── */}
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

          {isRunning ? (
            <button
              type="button"
              onClick={handleCancel}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/15
                         px-4 py-2 text-xs font-medium text-red-400 transition-colors
                         hover:bg-red-500/25 hover:text-red-300"
            >
              <XCircle className="h-3.5 w-3.5" />
              Cancel Download
            </button>
          ) : (
            <button
              type="button"
              onClick={handleFetch}
              disabled={selectedYears.length === 0}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
                selectedYears.length === 0
                  ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                  : 'bg-cyan-600 text-white hover:bg-cyan-500',
              )}
            >
              {fetching ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Image className="h-3.5 w-3.5" />
              )}
              Fetch Images
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
