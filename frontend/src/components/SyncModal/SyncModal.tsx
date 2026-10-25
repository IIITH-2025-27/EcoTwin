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
  getEmbeddingMergeOptions,
  getEmbeddingProgress,
  startEmbeddingGeneration,
  type GenerateEmbeddingsResponse,
  type EmbeddingProgressResponse,
} from '@/api/embeddings';

interface SyncModalProps {
  onClose: () => void;
}

const POLL_MS = 2000;
const ACTIVE: EmbeddingProgressResponse['status'][] = ['running', 'cancelling'];

/** Readable labels for the backend's current_step values. */
const STEP_LABELS: Record<string, string> = {
  checking_resume: 'checking existing embedding',
  loading_geotiff: 'loading image',
  reading_polygon: 'reading lake polygon',
  building_token_windows: 'building lake / shore tokens',
  inferring: 'running Prithvi',
  storing: 'saving',
};

// ── Main modal ────────────────────────────────────────────────────────────
export default function SyncModal({ onClose }: SyncModalProps) {
  const [yearStart, setYearStart] = useState<number>(2015);
  const [yearEnd, setYearEnd] = useState<number>(2025);
  const [selectedYears, setSelectedYears] = useState<number[]>([2025]);
  const [result, setResult] = useState<GenerateEmbeddingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lakeWeight, setLakeWeight] = useState<number | null>(null);

  const [starting, setStarting] = useState(false);
  const [progress, setProgress] = useState<EmbeddingProgressResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // ── Lock scroll ────────────────────────────────────────────────────────
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
      const p = await getEmbeddingProgress();
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

  // ── Load config, weight in use, and any run already in progress ────────
  useEffect(() => {
    mountedRef.current = true;
    fetchSyncCountry()
      .then((config) => {
        if (!mountedRef.current) return;
        setYearStart(config.year_start);
        setYearEnd(config.year_end);
        setSelectedYears([config.year_end]);
      })
      .catch((err: unknown) => {
        if (mountedRef.current) setError(err instanceof Error ? err.message : 'Could not load configuration.');
      });
    getEmbeddingMergeOptions()
      .then((opts) => mountedRef.current && setLakeWeight(opts.current_lake_weight ?? opts.default_lake_weight))
      .catch(() => {});
    getEmbeddingProgress()
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

  const yearOptions = Array.from({ length: yearEnd - yearStart + 1 }, (_, i) => yearEnd - i);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year)
        ? prev.filter((y) => y !== year)
        : [...prev, year].sort((a, b) => a - b),
    );
  };

  // ── Start ──────────────────────────────────────────────────────────────
  const handleStart = async () => {
    if (selectedYears.length === 0) {
      setError('Please select at least one year.');
      return;
    }

    setError(null);
    setStarting(true);
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
      setError(err instanceof Error ? err.message : 'Failed to start embedding generation.');
    } finally {
      setStarting(false);
    }
  };

  // ── Progress derived ───────────────────────────────────────────────────
  const total      = progress?.total ?? 0;
  const processed  = progress?.processed ?? 0;
  const successCnt = progress?.success ?? 0;
  const failedCnt  = progress?.failed ?? 0;
  const skippedCnt = progress?.skipped ?? 0;
  const pct        = total > 0 ? Math.min(100, Math.round((100 * processed) / total)) : 0;
  const isActive   = progress != null && ACTIVE.includes(progress.status);
  const isCancelling = progress?.status === 'cancelling';
  const isDone     = progress?.status === 'done';
  const isFailed   = progress?.status === 'failed';
  const isCancelled = progress?.status === 'cancelled';
  const isRunning  = isActive || starting;

  const handleCancel = async () => {
    setError(null);
    try {
      await cancelEmbeddingGeneration();
      // Keep polling: cancelling → cancelled once the current lake-year is done
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel embedding generation.');
    }
  };

  const statusLabel = (() => {
    if (!progress) return '';
    if (isCancelling) return 'Cancelling — finishing the current lake-year…';
    if (isActive) {
      if (total === 0) return 'Preparing lake list…';
      if (progress.current_lake_id) {
        const step = progress.current_step ? ` · ${STEP_LABELS[progress.current_step] ?? progress.current_step}` : '';
        return `Lake ${progress.current_lake_id}${progress.current_year ? ` / ${progress.current_year}` : ''}${step}`;
      }
      return 'Starting…';
    }
    if (isDone) return failedCnt > 0 ? 'Finished with failures' : 'Embedding generation complete';
    if (isCancelled) return 'Embedding generation cancelled';
    if (isFailed) return 'Embedding generation failed';
    return '';
  })();

  const runWeight = progress?.lake_weight ?? lakeWeight;

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget && !starting) onClose(); }}
    >
      <div className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl scrollbar-thin">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary-600/30 bg-primary-600/20">
              <RefreshCw className={clsx('h-4 w-4 text-primary-400', isRunning && 'animate-spin')} />
            </div>
            <div>
              <h2 id="sync-modal-title" className="text-sm font-semibold text-slate-100">
                Generate Embeddings
              </h2>
              <p className="text-xs text-slate-500">
                Prithvi lake + shore embeddings from local merged lake images
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
              Uses the merged 30 m lake GeoTIFFs (12-band stack) recorded in
              lake_images. Prithvi encodes the 480 m tokens covering each lake and
              its 500 m shore ring (B2, B3, B4, B8A, B11, B12); the lake and shore
              embeddings are pooled separately, stored, and blended into one
              embedding per lake and year.
            </p>
            {runWeight != null && (
              <p className="mt-1.5 text-[10px] text-slate-500">
                Blended with lake weight{' '}
                <span className="text-slate-300">{Math.round(runWeight * 100)}%</span> / shore{' '}
                <span className="text-slate-300">{Math.round((1 - runWeight) * 100)}%</span> — the
                weight already in use. Change it for all years in Merge Embeddings.
              </p>
            )}
            <p className="mt-1 text-[10px] text-slate-500">
              Lake-years with an embedding newer than their image are skipped.
            </p>
          </div>

          {progress && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="flex min-w-0 items-center gap-1.5 text-slate-400">
                  {isActive && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary-400" />}
                  <span className="truncate">{statusLabel}</span>
                </span>
                <span className="shrink-0 font-mono text-slate-300">
                  {processed} / {total} · {pct}%
                </span>
              </div>

              <div
                className="h-2 overflow-hidden rounded-full bg-slate-700/60"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={pct}
              >
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500 ease-out',
                    isDone && failedCnt === 0
                      ? 'bg-emerald-500'
                      : isDone
                      ? 'bg-amber-500'
                      : isFailed || isCancelled || isCancelling
                      ? 'bg-red-500'
                      : 'bg-primary-500',
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>

              <div className="flex gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {successCnt} generated
                </span>
                <span className="flex items-center gap-1 text-slate-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {skippedCnt} up to date
                </span>
                <span className="flex items-center gap-1 text-red-400">
                  <XCircle className="h-3 w-3" />
                  {failedCnt} failed
                </span>
              </div>

              {progress.errors.length > 0 && (
                <div className="max-h-24 overflow-y-auto rounded-lg border border-red-500/30 bg-red-500/5 p-2">
                  {progress.errors.length > 5 && (
                    <p className="mb-1 text-[10px] text-red-300">
                      Showing last 5 of {progress.errors.length} errors
                    </p>
                  )}
                  {progress.errors.slice(-5).map((e, i) => (
                    <p key={i} className="text-[10px] leading-relaxed text-red-400">
                      {e}
                    </p>
                  ))}
                </div>
              )}

              {isActive && (
                <p className="text-[10px] text-slate-500">
                  You can close this dialog — generation keeps running and progress is shown
                  again when you reopen it.
                </p>
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
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/15
                         px-4 py-2 text-xs font-medium text-red-400 transition-colors
                         hover:bg-red-500/25 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isCancelling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5" />}
              {isCancelling ? 'Cancelling...' : 'Cancel Embeddings'}
            </button>
          ) : (
            <button
              type="button"
              id="sync-data-btn"
              onClick={handleStart}
              disabled={selectedYears.length === 0 || starting}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
                selectedYears.length === 0 || starting
                  ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                  : 'bg-primary-600 text-white hover:bg-primary-500',
              )}
            >
              {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Image className="h-3.5 w-3.5" />}
              Get Embeddings
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
