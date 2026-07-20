import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Layers,
  Loader2,
  X,
  XCircle,
  CheckCircle2,
  AlertTriangle,
  FolderOutput,
  Trash2,
} from 'lucide-react';
import { clsx } from 'clsx';

import {
  getMergeOptions,
  startMergeTiles,
  getMergeProgress,
  type MergeYearOption,
  type MergeProgress,
  type MergeTilesResponse,
} from '@/api/imagery';

interface MergeTilesModalProps {
  onClose: () => void;
}

export default function MergeTilesModal({ onClose }: MergeTilesModalProps) {
  // ── Options fetched from backend ────────────────────────────────────────
  const [availableYears, setAvailableYears] = useState<MergeYearOption[]>([]);
  const [dataRoot, setDataRoot] = useState<string>('');
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  // ── User selections ────────────────────────────────────────────────────
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [deleteTiles, setDeleteTiles] = useState(false);

  // ── Merge state ────────────────────────────────────────────────────────
  const [merging, setMerging] = useState(false);
  const [result, setResult] = useState<MergeTilesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<MergeProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Prevent body scroll ────────────────────────────────────────────────
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  // ── Fetch available years on mount ─────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const opts = await getMergeOptions();
        if (cancelled) return;
        setAvailableYears(opts.years);
        setDataRoot(opts.data_root);
        // Auto-select the first year if available
        if (opts.years.length > 0) {
          setSelectedYears([opts.years[0].year]);
        }
      } catch (err) {
        if (!cancelled) {
          setOptionsError(
            err instanceof Error ? err.message : 'Failed to load merge options.',
          );
        }
      } finally {
        if (!cancelled) setLoadingOptions(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Cleanup polling on unmount ─────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const p = await getMergeProgress();
        setProgress(p);
        if (p.status !== 'running') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setMerging(false);
        }
      } catch {
        // Silently retry
      }
    }, 2000);
  }, []);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year)
        ? prev.filter((y) => y !== year)
        : [...prev, year].sort((a, b) => a - b),
    );
  };

  const handleMerge = async () => {
    if (selectedYears.length === 0) {
      setError('Please select at least one year.');
      return;
    }

    setMerging(true);
    setError(null);
    setResult(null);
    setProgress(null);

    try {
      const res = await startMergeTiles({
        years: selectedYears,
        delete_tiles: deleteTiles,
      });
      setResult(res);
      startPolling();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Failed to start tile merge.',
      );
      setMerging(false);
    }
  };

  // ── Derived state ──────────────────────────────────────────────────────
  const progressPercent =
    progress && progress.total > 0
      ? Math.round((progress.processed / progress.total) * 100)
      : 0;

  const isRunning = progress?.status === 'running' || merging;
  const isDone = progress?.status === 'done';
  const isFailed = progress?.status === 'failed';

  // Build a summary of selected years + lake counts
  const selectedSummary = availableYears
    .filter((y) => selectedYears.includes(y.year))
    .map((y) => `${y.year} (${y.lake_count} lake${y.lake_count !== 1 ? 's' : ''})`)
    .join(', ');

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-tiles-title"
      onClick={(event) => {
        if (event.target === event.currentTarget && !isRunning) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/15">
              <Layers className="h-4 w-4 text-amber-400" />
            </div>
            <div>
              <h2
                id="merge-tiles-title"
                className="text-sm font-semibold text-slate-100"
              >
                Merge Lake Tiles
              </h2>
              <p className="text-xs text-slate-500">
                Combine downloaded tiles into single GeoTIFFs per lake
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
          {/* Loading state */}
          {loadingOptions && (
            <div className="flex items-center justify-center gap-2 py-6 text-xs text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading available years…
            </div>
          )}

          {/* Options error */}
          {optionsError && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              {optionsError}
            </div>
          )}

          {/* No data */}
          {!loadingOptions && !optionsError && availableYears.length === 0 && (
            <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-4 text-center text-xs text-slate-400">
              <AlertTriangle className="mx-auto mb-2 h-5 w-5 text-amber-400" />
              No completed tile downloads found. Fetch satellite images first,
              then come back to merge.
            </div>
          )}

          {/* Year selector */}
          {!loadingOptions && !optionsError && availableYears.length > 0 && (
            <>
              <div>
                <label className="mb-2 block text-xs font-medium text-slate-300">
                  Select years to merge
                </label>
                <div className="flex flex-wrap gap-2">
                  {availableYears.map((opt) => {
                    const isSelected = selectedYears.includes(opt.year);
                    return (
                      <button
                        key={opt.year}
                        onClick={() => !isRunning && toggleYear(opt.year)}
                        disabled={isRunning}
                        className={clsx(
                          'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                          isSelected
                            ? 'border-amber-500/50 bg-amber-500/20 text-amber-300 shadow-sm shadow-amber-500/10'
                            : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                          isRunning && 'cursor-not-allowed opacity-60',
                        )}
                      >
                        <span>{opt.year}</span>
                        <span className="ml-1.5 text-[10px] opacity-70">
                          {opt.lake_count} lake{opt.lake_count !== 1 ? 's' : ''}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Output path info */}
              <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-300">
                  <FolderOutput className="h-3.5 w-3.5 text-slate-400" />
                  Output location
                </div>
                <p className="font-mono text-[11px] leading-relaxed text-slate-400">
                  {dataRoot}/
                  <span className="text-amber-400">{'{year}'}</span>/lake_
                  <span className="text-amber-400">{'{lake_id}'}</span>.tif
                </p>
                {selectedSummary && (
                  <p className="mt-1.5 text-[10px] text-slate-500">
                    Selected: {selectedSummary}
                  </p>
                )}
              </div>

              {/* Delete tiles toggle */}
              <label
                className={clsx(
                  'flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors',
                  deleteTiles
                    ? 'border-red-500/30 bg-red-500/5'
                    : 'border-slate-700/60 bg-surface-800',
                  isRunning && 'cursor-not-allowed opacity-60',
                )}
              >
                <input
                  type="checkbox"
                  checked={deleteTiles}
                  onChange={(e) => !isRunning && setDeleteTiles(e.target.checked)}
                  disabled={isRunning}
                  className="sr-only"
                />
                <div
                  className={clsx(
                    'flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors',
                    deleteTiles
                      ? 'border-red-500/50 bg-red-500/20'
                      : 'border-slate-600 bg-surface-700',
                  )}
                >
                  {deleteTiles && <Trash2 className="h-3 w-3 text-red-400" />}
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-300">
                    Delete tile files after merge
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {deleteTiles
                      ? 'Individual tile GeoTIFFs will be removed after successful merge'
                      : 'Tile files will be kept on disk alongside the merged file'}
                  </p>
                </div>
              </label>
            </>
          )}

          {/* Progress bar */}
          {progress && progress.status !== 'idle' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  {isRunning && progress.current_lake_id
                    ? `Merging lake ${progress.current_lake_id} / ${progress.current_year}`
                    : isDone
                    ? 'Merge complete'
                    : isFailed
                    ? 'Merge finished with errors'
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
                      : isFailed
                      ? 'bg-red-500'
                      : 'bg-amber-500',
                  )}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              {/* Stats chips */}
              <div className="flex gap-3 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {progress.success} merged
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
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
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

          <button
            type="button"
            onClick={handleMerge}
            disabled={
              isRunning ||
              selectedYears.length === 0 ||
              loadingOptions ||
              availableYears.length === 0
            }
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              isRunning ||
                selectedYears.length === 0 ||
                loadingOptions ||
                availableYears.length === 0
                ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                : 'bg-amber-600 text-white hover:bg-amber-500',
            )}
          >
            {merging ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Layers className="h-3.5 w-3.5" />
            )}
            Start Merge
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
