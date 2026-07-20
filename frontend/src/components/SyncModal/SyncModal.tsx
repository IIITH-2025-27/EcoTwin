import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Image,
  Loader2,
  RefreshCw,
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';

import { fetchSyncCountry } from '@/api/sync';
import {
  cancelEmbeddingGeneration,
  getEmbeddingProgress,
  startEmbeddingGeneration,
  type GenerateEmbeddingsResponse,
  type EmbeddingProgressResponse,
} from '@/api/embeddings';

interface SyncModalProps {
  onClose: () => void;
}

// ── Main modal ────────────────────────────────────────────────────────────
export default function SyncModal({ onClose }: SyncModalProps) {
  const [yearStart, setYearStart] = useState<number>(2015);
  const [yearEnd, setYearEnd] = useState<number>(2025);
  const [selectedYears, setSelectedYears] = useState<number[]>([2025]);
  const [result, setResult] = useState<GenerateEmbeddingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [progress, setProgress] = useState<EmbeddingProgressResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load config + states on mount ─────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const config = await fetchSyncCountry();
        if (cancelled) return;
        setYearStart(config.year_start);
        setYearEnd(config.year_end);
        setSelectedYears([config.year_end]);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load configuration.');
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  // ── Lock scroll ────────────────────────────────────────────────────────
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const p = await getEmbeddingProgress();
        setProgress(p);
        if (p.status !== 'running') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setSyncing(false);
          setCancelling(false);
        }
      } catch {
        // Keep polling and retry on the next interval.
      }
    }, 2000);
  }, []);

  const yearOptions = Array.from({ length: yearEnd - yearStart + 1 }, (_, i) => yearEnd - i);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year)
        ? prev.filter((y) => y !== year)
        : [...prev, year].sort((a, b) => a - b),
    );
  };

  // ── Sync handler ───────────────────────────────────────────────────────
  const handleSync = async () => {
    if (selectedYears.length === 0) {
      setError('Please select at least one year.');
      return;
    }

    setError(null);
    setSyncing(true);
    setCancelling(false);
    setResult(null);
    setProgress(null);

    try {
      const res = await startEmbeddingGeneration({
        lake_ids: null,
        years: selectedYears,
        confirmed: true,
      });
      setResult(res);
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start synchronization.');
      setSyncing(false);
    }
  };

  // ── Progress derived ───────────────────────────────────────────────────
  const total      = progress?.total ?? 0;
  const processed  = progress?.processed ?? 0;
  const successCnt = progress?.success ?? 0;
  const failedCnt  = progress?.failed ?? 0;
  const skippedCnt = progress?.skipped ?? 0;
  const pct        = total > 0 ? Math.round((100 * processed) / total) : 0;
  const isDone     = progress?.status === 'done';
  const isFailed   = progress?.status === 'failed';
  const isCancelled = progress?.status === 'cancelled';
  const isRunning  = progress?.status === 'running' || syncing;

  const handleCancel = async () => {
    if (!isRunning) return;
    setError(null);
    setCancelling(true);
    try {
      await cancelEmbeddingGeneration();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel synchronization.');
      setCancelling(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget && !isRunning && !cancelling) onClose(); }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary-600/30 bg-primary-600/20">
              <RefreshCw className={clsx('h-4 w-4 text-primary-400', (syncing || isRunning) && 'animate-spin')} />
            </div>
            <div>
              <h2 id="sync-modal-title" className="text-sm font-semibold text-slate-100">
                Sync Lake Data
              </h2>
              <p className="text-xs text-slate-500">
                Generate embeddings from local merged lake images
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isRunning || cancelling}
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

          <div>
            <label className="mb-2 block text-xs font-medium text-slate-300">
              Select years for embedding generation
            </label>
            <div className="flex flex-wrap gap-2">
              {yearOptions.map((year) => {
                const isSelected = selectedYears.includes(year);
                return (
                  <button
                    key={year}
                    onClick={() => !isRunning && toggleYear(year)}
                    disabled={isRunning}
                    className={clsx(
                      'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                      isSelected
                        ? 'border-primary-500/50 bg-primary-500/20 text-primary-300 shadow-sm shadow-primary-500/10'
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

          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <p className="text-xs leading-relaxed text-slate-400">
              Uses locally merged lake GeoTIFFs from completed lake_images records.
              For each lake boundary, the backend creates 1km x 1km cells, keeps
              only cells above configured lake-coverage threshold, runs Prithvi,
              and stores outputs into sub_regions and sub_region_features.
            </p>
          </div>

          {progress && progress.status !== 'idle' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  {isRunning && progress.current_lake_id
                    ? `Processing lake ${progress.current_lake_id}${progress.current_year ? ` / ${progress.current_year}` : ''}${progress.current_step ? ` - ${progress.current_step}` : ''}`
                    : isDone
                    ? 'Embedding generation complete'
                    : isCancelled
                    ? 'Embedding generation cancelled'
                    : isFailed
                    ? 'Embedding generation failed'
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
                      : isFailed || isCancelled
                      ? 'bg-red-500'
                      : 'bg-primary-500',
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="flex gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {successCnt} ok
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
            <div className="rounded-lg border border-primary-500/30 bg-primary-500/10 p-3 text-xs text-primary-300">
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

          {isRunning ? (
            <button
              type="button"
              onClick={handleCancel}
              disabled={cancelling}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/15
                         px-4 py-2 text-xs font-medium text-red-400 transition-colors
                         hover:bg-red-500/25 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {cancelling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5" />}
              {cancelling ? 'Cancelling...' : 'Cancel Embeddings'}
            </button>
          ) : (
            <button
              type="button"
              id="sync-data-btn"
              onClick={handleSync}
              disabled={selectedYears.length === 0}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
                selectedYears.length === 0
                  ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                  : 'bg-primary-600 text-white hover:bg-primary-500',
              )}
            >
              {syncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Image className="h-3.5 w-3.5" />}
              Get Embeddings
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
