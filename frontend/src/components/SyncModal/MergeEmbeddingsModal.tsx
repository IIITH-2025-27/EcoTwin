import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Layers, Loader2, X, CheckCircle2, Globe2, AlertTriangle, XCircle, Scale } from 'lucide-react';
import { clsx } from 'clsx';

import {
  getEmbeddingMergeOptions,
  getMergeEmbeddingProgress,
  mergeEmbeddings,
  type EmbeddingMergeOptions,
  type MergeEmbeddingProgress,
} from '@/api/embeddings';

interface MergeEmbeddingsModalProps {
  onClose: () => void;
}

const SUPPORTED_COUNTRIES = ['India'];
const POLL_MS = 1500;

/** Quick picks for the lake weight w. */
const PRESETS: { w: number; label: string }[] = [
  { w: 1.0, label: 'Lake only' },
  { w: 0.85, label: '0.85' },
  { w: 0.7, label: '0.7' },
  { w: 0.5, label: 'Equal' },
];

const pct = (w: number) => `${Math.round(w * 100)}%`;
const fmtW = (w: number) => w.toFixed(2).replace(/0$/, '');

export default function MergeEmbeddingsModal({ onClose }: MergeEmbeddingsModalProps) {
  const [selectedCountry, setSelectedCountry] = useState('India');
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [options, setOptions] = useState<EmbeddingMergeOptions | null>(null);
  const [lakeWeight, setLakeWeight] = useState<number>(0.7);
  const [starting, setStarting] = useState(false);
  const [loadingYears, setLoadingYears] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<MergeEmbeddingProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const loadOptions = useCallback(async (resetSelection: boolean) => {
    setLoadingYears(true);
    try {
      const opts = await getEmbeddingMergeOptions();
      if (!mountedRef.current) return;
      setOptions(opts);
      if (resetSelection) {
        // All years by default: every lake-year should use the same weight
        setSelectedYears(opts.years);
        setLakeWeight(opts.current_lake_weight ?? opts.default_lake_weight);
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Unable to load available embedding years.');
      }
    } finally {
      if (mountedRef.current) setLoadingYears(false);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) clearTimeout(pollRef.current);
    pollRef.current = null;
  }, []);

  // Chained timeouts so slow responses never overlap
  const poll = useCallback(async () => {
    try {
      const p = await getMergeEmbeddingProgress();
      if (!mountedRef.current) return;
      setProgress(p);
      if (p.status !== 'running') {
        stopPolling();
        if (p.status === 'done') void loadOptions(false);
        return;
      }
    } catch {
      // Retry on the next tick
    }
    pollRef.current = setTimeout(poll, POLL_MS);
  }, [stopPolling, loadOptions]);

  const startPolling = useCallback(() => {
    stopPolling();
    void poll();
  }, [poll, stopPolling]);

  useEffect(() => {
    mountedRef.current = true;
    void loadOptions(true);
    getMergeEmbeddingProgress()
      .then((p) => {
        if (!mountedRef.current) return;
        if (p.status === 'running') {
          setProgress(p);
          startPolling();
        }
      })
      .catch(() => {});
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [loadOptions, startPolling, stopPolling]);

  const availableYears = options?.years ?? [];
  const yearInfo = (year: number) => options?.year_details.find((y) => y.year === year);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year) ? prev.filter((item) => item !== year) : [...prev, year].sort((a, b) => a - b),
    );
  };

  const isRunning = progress?.status === 'running' || starting;
  const isDone = progress?.status === 'done';
  const isFailed = progress?.status === 'failed';
  const showProgress = progress != null && (isRunning || isDone || isFailed);

  const validYears = selectedYears.filter((year) => availableYears.includes(year));
  const canMerge = !isRunning && !loadingYears && validYears.length > 0;
  const partialSelection = validYears.length > 0 && validYears.length < availableYears.length;

  // Weights the unselected years would keep — mixing weights makes
  // cross-year similarity / forecasts inconsistent.
  const otherWeights = new Set<number>();
  availableYears
    .filter((y) => !validYears.includes(y))
    .forEach((y) => yearInfo(y)?.weights.forEach((w) => otherWeights.add(w.lake_weight)));
  const mixedAfterMerge = [...otherWeights].some((w) => Math.abs(w - lakeWeight) > 1e-6);

  const handleMerge = async () => {
    if (validYears.length === 0) {
      setError('Please select at least one year.');
      return;
    }
    setStarting(true);
    setError(null);
    try {
      await mergeEmbeddings({
        years: validYears,
        country: selectedCountry,
        lake_weight: Math.round(lakeWeight * 100) / 100,
        confirmed: true,
      });
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start embedding merge.');
    } finally {
      setStarting(false);
    }
  };

  const total = progress?.total ?? 0;
  const processed = progress?.processed ?? 0;
  const pctDone = total > 0 ? Math.min(100, Math.round((100 * processed) / total)) : 0;

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
      <div className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl scrollbar-thin">
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
                Combine the stored lake and shore embeddings with your weighting (no GPU)
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
          </div>

          {/* Lake / shore weighting */}
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <label className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-300">
              <Scale className="h-3.5 w-3.5 text-slate-400" />
              Lake / shore weighting
            </label>

            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="text-sky-300">Lake {pct(lakeWeight)}</span>
              <span className="text-amber-300">Shore {pct(1 - lakeWeight)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={lakeWeight}
              disabled={isRunning}
              onChange={(e) => setLakeWeight(Number(e.target.value))}
              aria-label="Lake weight"
              aria-valuetext={`Lake ${pct(lakeWeight)}, shore ${pct(1 - lakeWeight)}`}
              className="w-full accent-emerald-500 disabled:opacity-60"
            />
            {/* Split bar */}
            <div className="mt-1 flex h-1.5 overflow-hidden rounded-full" aria-hidden>
              <div className="bg-sky-500/70" style={{ width: pct(lakeWeight) }} />
              <div className="bg-amber-500/70" style={{ width: pct(1 - lakeWeight) }} />
            </div>

            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.w}
                  type="button"
                  disabled={isRunning}
                  onClick={() => setLakeWeight(p.w)}
                  className={clsx(
                    'rounded-md border px-2 py-1 text-[10px] font-medium transition-colors',
                    Math.abs(lakeWeight - p.w) < 1e-6
                      ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300'
                      : 'border-slate-700/60 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                    isRunning && 'cursor-not-allowed opacity-60',
                  )}
                >
                  {p.label}
                  {options && Math.abs(p.w - options.default_lake_weight) < 1e-6 && ' (default)'}
                </button>
              ))}
            </div>

            <p className="mt-2.5 font-mono text-[10px] text-slate-400">
              embedding = normalize({fmtW(lakeWeight)} · lake + {fmtW(1 - lakeWeight)} · shore)
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
              Lake = Prithvi tokens inside the lake polygon; shore = the 500 m ring around it.
              Lake-years without valid shore pixels stay lake-only. Embeddings generated later
              use the weight in use, so they stay comparable.
              {options?.current_lake_weight != null && (
                <> Currently in use: <span className="text-slate-300">{fmtW(options.current_lake_weight)}</span>.</>
              )}
            </p>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs font-medium text-slate-300">Years to re-blend</label>
              {availableYears.length > 0 && (
                <button
                  type="button"
                  disabled={isRunning}
                  onClick={() =>
                    setSelectedYears(validYears.length === availableYears.length ? [] : availableYears)
                  }
                  className="text-[10px] text-slate-400 hover:text-slate-200 disabled:opacity-50"
                >
                  {validYears.length === availableYears.length ? 'Clear' : 'Select all'}
                </button>
              )}
            </div>
            {loadingYears && !options ? (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading available years...
              </div>
            ) : availableYears.length === 0 ? (
              <p className="text-xs text-slate-500">
                No lake / shore embeddings yet — run Generate Embeddings first.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {availableYears.map((year) => {
                  const isSelected = selectedYears.includes(year);
                  const info = yearInfo(year);
                  const weights = info?.weights.map((w) => fmtW(w.lake_weight)).join('/') || '—';
                  return (
                    <button
                      key={year}
                      type="button"
                      onClick={() => !isRunning && toggleYear(year)}
                      disabled={isRunning}
                      title={`${info?.lakes ?? 0} lake-years · lake weight ${weights}`}
                      className={clsx(
                        'rounded-lg border px-3 py-1.5 text-left text-xs font-medium transition-all',
                        isSelected
                          ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300'
                          : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
                        isRunning && 'cursor-not-allowed opacity-60',
                      )}
                    >
                      <span className="block">{year}</span>
                      <span className="block text-[9px] font-normal opacity-70">
                        {info?.lakes ?? 0} lakes · w {weights}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            {partialSelection && mixedAfterMerge && (
              <p className="mt-2 flex items-start gap-1 text-[10px] text-amber-400">
                <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
                The unselected years keep a different weight. Similarity and forecasts compare
                across years, so re-blend all years with the same weight.
              </p>
            )}
          </div>

          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              {error}
            </div>
          )}
        </div>

        {showProgress && progress && (
          <div className="space-y-2 border-t border-slate-700/60 px-5 py-4">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">
                {isRunning && progress.current_lake_id
                  ? `Re-blending lake ${progress.current_lake_id}${progress.current_year ? ` / ${progress.current_year}` : ''}`
                  : isRunning
                  ? 'Starting merge...'
                  : isDone
                  ? `Merged with lake weight ${progress.lake_weight != null ? fmtW(progress.lake_weight) : '—'}`
                  : 'Embedding merge failed'}
              </span>
              <span className="font-mono text-slate-300">
                {total > 0 ? `${processed} / ${total} · ${pctDone}%` : '0 / …'}
              </span>
            </div>

            <div
              className="h-2 overflow-hidden rounded-full bg-slate-700/60"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pctDone}
            >
              <div
                className={clsx(
                  'h-full rounded-full transition-all duration-500 ease-out',
                  isFailed ? 'bg-red-500' : 'bg-emerald-500',
                )}
                style={{ width: `${isDone ? 100 : pctDone}%` }}
              />
            </div>

            <div className="flex flex-wrap gap-3 text-[10px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle2 className="h-3 w-3" />
                {progress.success} merged
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
            disabled={!canMerge}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              !canMerge
                ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                : 'bg-emerald-600 text-white hover:bg-emerald-500',
            )}
          >
            {isRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
            {isRunning ? 'Merging...' : `Merge with lake ${pct(lakeWeight)}`}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
