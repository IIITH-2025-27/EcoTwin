import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Layers, Loader2, X, CheckCircle2, Globe2, AlertTriangle, XCircle } from 'lucide-react';
import { clsx } from 'clsx';

import {
  getAvailableEmbeddingYears,
  getMergeEmbeddingProgress,
  mergeEmbeddings,
  type MergeEmbeddingProgress,
} from '@/api/embeddings';

interface MergeEmbeddingsModalProps {
  onClose: () => void;
}

const SUPPORTED_COUNTRIES = ['India'];

export default function MergeEmbeddingsModal({ onClose }: MergeEmbeddingsModalProps) {
  const [selectedCountry, setSelectedCountry] = useState('India');
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [merging, setMerging] = useState(false);
  const [loadingYears, setLoadingYears] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<MergeEmbeddingProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const pollProgress = useCallback(async () => {
    try {
      const p = await getMergeEmbeddingProgress();
      setProgress(p);
      if (p.status === 'done' || p.status === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setMerging(false);
      }
      return p;
    } catch {
      return null;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    void pollProgress();
    pollRef.current = setInterval(() => {
      void pollProgress();
    }, 2000);
  }, [pollProgress]);

  useEffect(() => {
    let ignore = false;

    const fetchAvailableYears = async () => {
      setLoadingYears(true);
      setError(null);

      try {
        const years = await getAvailableEmbeddingYears();
        if (!ignore) {
          setAvailableYears(years);
          setSelectedYears((previous) => previous.filter((year) => years.includes(year)));
        }
      } catch (err: unknown) {
        if (!ignore) {
          setAvailableYears([]);
          setSelectedYears([]);
          setError(err instanceof Error ? err.message : 'Unable to load available embedding years.');
        }
      } finally {
        if (!ignore) {
          setLoadingYears(false);
        }
      }
    };

    const checkExistingMerge = async () => {
      try {
        const p = await getMergeEmbeddingProgress();
        if (ignore) return;
        if (p.status === 'running') {
          setProgress(p);
          setMerging(true);
          startPolling();
        }
      } catch {
        // Ignore — merge status is optional on open.
      }
    };

    void fetchAvailableYears();
    void checkExistingMerge();

    return () => {
      ignore = true;
    };
  }, [startPolling]);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year) ? prev.filter((item) => item !== year) : [...prev, year].sort((a, b) => a - b),
    );
  };

  const handleMerge = async () => {
    const filteredYears = selectedYears.filter((year) => availableYears.includes(year));

    if (filteredYears.length === 0) {
      setError('Please select at least one available year for the selected region.');
      return;
    }

    setMerging(true);
    setError(null);
    setProgress({
      status: 'running',
      total: 0,
      processed: 0,
      success: 0,
      failed: 0,
      skipped: 0,
      current_lake_id: null,
      current_year: null,
      errors: [],
    });

    try {
      await mergeEmbeddings({
        years: filteredYears,
        country: selectedCountry,
        confirmed: true,
      });
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start embedding merge.');
      setMerging(false);
      setProgress(null);
    }
  };

  const total = progress?.total ?? 0;
  const processed = progress?.processed ?? 0;
  const pending = Math.max(total - processed, 0);
  const successCnt = progress?.success ?? 0;
  const failedCnt = progress?.failed ?? 0;
  const skippedCnt = progress?.skipped ?? 0;
  const pct = total > 0 ? Math.round((100 * processed) / total) : 0;
  const isDone = progress?.status === 'done';
  const isFailed = progress?.status === 'failed';
  const isRunning = progress?.status === 'running' || merging;
  const showProgress = isRunning || isDone || isFailed;

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-embeddings-title"
      onClick={(event) => {
        if (event.target === event.currentTarget && !isRunning) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/15">
              <Layers className={clsx('h-4 w-4 text-emerald-400', isRunning && 'animate-pulse')} />
            </div>
            <div>
              <h2 id="merge-embeddings-title" className="text-sm font-semibold text-slate-100">
                Merge Lake Embeddings
              </h2>
              <p className="text-xs text-slate-500">
                Aggregate tile embeddings into one embedding per lake and year
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

        <div className="space-y-4 px-5 py-4">
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <label className="mb-2 block text-xs font-medium text-slate-300">Country</label>
            <div className="flex items-center gap-2 rounded-lg border border-slate-700/60 bg-surface-900 px-3 py-2">
              <Globe2 className="h-4 w-4 text-slate-400" />
              <select
                value={selectedCountry}
                onChange={(e) => setSelectedCountry(e.target.value)}
                disabled={isRunning}
                className="w-full bg-transparent text-sm text-slate-200 outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                {SUPPORTED_COUNTRIES.map((country) => (
                  <option key={country} value={country}>{country}</option>
                ))}
              </select>
            </div>
            <p className="mt-2 text-[10px] text-slate-500">Currently India is supported; the selector is ready for future countries.</p>
          </div>

          <div>
            <label className="mb-2 block text-xs font-medium text-slate-300">Select years to merge</label>
            {loadingYears ? (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading available years...
              </div>
            ) : availableYears.length === 0 ? (
              <p className="text-xs text-slate-500">No completed subregion embeddings are available for merge yet.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {availableYears.map((year) => {
                  const isSelected = selectedYears.includes(year);
                  return (
                    <button
                      key={year}
                      type="button"
                      onClick={() => !isRunning && toggleYear(year)}
                      disabled={isRunning}
                      className={clsx(
                        'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                        isSelected
                          ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300'
                          : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                        isRunning && 'cursor-not-allowed opacity-60',
                      )}
                    >
                      {year}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              {error}
            </div>
          )}
        </div>

        {showProgress && (
          <div className="space-y-2 border-t border-slate-700/60 px-5 py-4">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">
                {isRunning && progress?.current_lake_id
                  ? `Merging lake ${progress.current_lake_id}${progress.current_year ? ` / ${progress.current_year}` : ''}`
                  : isRunning
                  ? 'Starting merge...'
                  : isDone
                  ? 'Embedding merge complete'
                  : isFailed
                  ? 'Embedding merge failed'
                  : 'Processing...'}
              </span>
              <span className="font-mono text-slate-300">
                {total > 0 ? `${processed} / ${total}` : '0 / …'}
              </span>
            </div>

            <div className="h-2 overflow-hidden rounded-full bg-slate-700/60">
              <div
                className={clsx(
                  'h-full rounded-full transition-all duration-500 ease-out',
                  isDone ? 'bg-emerald-500' : isFailed ? 'bg-red-500' : 'bg-emerald-500',
                )}
                style={{ width: total > 0 ? `${pct}%` : '0%' }}
              />
            </div>

            <div className="flex flex-wrap gap-3 text-[10px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle2 className="h-3 w-3" />
                {successCnt} merged
              </span>
              <span className="flex items-center gap-1 text-amber-400">
                <AlertTriangle className="h-3 w-3" />
                {skippedCnt} skipped
              </span>
              <span className="flex items-center gap-1 text-red-400">
                <XCircle className="h-3 w-3" />
                {failedCnt} failed
              </span>
              {isRunning && total > 0 && (
                <span className="flex items-center gap-1 text-slate-400">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {pending} pending
                </span>
              )}
            </div>

            {(progress?.errors.length ?? 0) > 0 && (
              <div className="max-h-24 overflow-y-auto rounded-lg border border-red-500/30 bg-red-500/5 p-2">
                {progress!.errors.slice(-5).map((e, i) => (
                  <p key={i} className="text-[10px] leading-relaxed text-red-400">
                    {e}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

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
            onClick={handleMerge}
            disabled={
              isRunning
              || loadingYears
              || availableYears.length === 0
              || selectedYears.filter((year) => availableYears.includes(year)).length === 0
            }
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              isRunning
              || loadingYears
              || availableYears.length === 0
              || selectedYears.filter((year) => availableYears.includes(year)).length === 0
                ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                : 'bg-emerald-600 text-white hover:bg-emerald-500',
            )}
          >
            {isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
            {isRunning ? 'Merging...' : 'Merge Embeddings'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
