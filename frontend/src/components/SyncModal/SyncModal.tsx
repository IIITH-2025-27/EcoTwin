import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Database,
  Loader2,
  RefreshCw,
  X,
  CheckCircle2,
  AlertCircle,
  Calendar,
  Layers,
  ChevronDown,
  MapPin,
} from 'lucide-react';
import { clsx } from 'clsx';

import { getLakeCount } from '@/api/regions';
import {
  fetchSyncCountry,
  fetchLakeStates,
  startSync,
  cancelSync,
  getSyncProgress,
  type SyncProgressResponse,
} from '@/api/sync';

interface SyncModalProps {
  onClose: () => void;
}

// ── State multiselect component ───────────────────────────────────────────
function StateMultiSelect({
  states,
  selected,
  onChange,
  loading,
}: {
  states: string[];
  selected: string[];
  onChange: (v: string[]) => void;
  loading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggle = (state: string) => {
    onChange(selected.includes(state) ? selected.filter((s) => s !== state) : [...selected, state]);
  };

  const selectAll = () => onChange([...states]);
  const clearAll = () => onChange([]);

  const label =
    selected.length === 0
      ? 'All States'
      : selected.length === states.length
      ? 'All States'
      : selected.length === 1
      ? selected[0]
      : `${selected.length} states selected`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={loading}
        className={clsx(
          'flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm transition-colors',
          open
            ? 'border-primary-500 bg-surface-800 text-slate-100'
            : 'border-slate-700/60 bg-surface-800 text-slate-300 hover:border-slate-600',
        )}
      >
        <span className="flex items-center gap-1.5 min-w-0">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          <span className="truncate text-xs">{loading ? 'Loading states…' : label}</span>
        </span>
        {selected.length > 0 && selected.length < states.length && (
          <span className="shrink-0 rounded-full bg-primary-600/30 px-1.5 py-0.5 text-[10px] font-bold text-primary-300">
            {selected.length}
          </span>
        )}
        <ChevronDown className={clsx('h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-lg border border-slate-700/60 bg-surface-800 shadow-2xl">
          {/* Actions */}
          <div className="flex items-center justify-between border-b border-slate-700/40 px-3 py-1.5">
            <button type="button" onClick={selectAll} className="text-[11px] text-primary-400 hover:text-primary-300">
              Select all
            </button>
            <button type="button" onClick={clearAll} className="text-[11px] text-slate-500 hover:text-slate-300">
              Clear
            </button>
          </div>
          {/* List */}
          <ul className="max-h-44 overflow-y-auto py-1">
            {states.map((state) => {
              const checked = selected.includes(state);
              return (
                <li key={state}>
                  <button
                    type="button"
                    onClick={() => toggle(state)}
                    className={clsx(
                      'flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-xs transition-colors',
                      checked ? 'bg-primary-600/10 text-primary-300' : 'text-slate-300 hover:bg-slate-700/40',
                    )}
                  >
                    <span
                      className={clsx(
                        'flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border transition-colors',
                        checked ? 'border-primary-500 bg-primary-500' : 'border-slate-600',
                      )}
                    >
                      {checked && (
                        <svg viewBox="0 0 10 10" className="h-2.5 w-2.5 text-white" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="1.5,5 4,7.5 8.5,2" />
                        </svg>
                      )}
                    </span>
                    {state}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────
export default function SyncModal({ onClose }: SyncModalProps) {
  const [country, setCountry] = useState('India');
  const [yearStart, setYearStart] = useState<number>(2015);
  const [yearEnd, setYearEnd] = useState<number>(2025);
  const [maxYearRange, setMaxYearRange] = useState<number>(10);
  const [totalLakes, setTotalLakes] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Custom year range pickers
  const [syncStartYear, setSyncStartYear] = useState<number>(2025);
  const [syncEndYear, setSyncEndYear] = useState<number>(2025);

  // State multiselect
  const [availableStates, setAvailableStates] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [statesLoading, setStatesLoading] = useState(false);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [started, setStarted] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<SyncProgressResponse | null>(null);

  // ── Load config + states on mount ─────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const config = await fetchSyncCountry();
        if (cancelled) return;
        setCountry(config.country);
        setYearStart(config.year_start);
        setYearEnd(config.year_end);
        setMaxYearRange(config.max_year_range ?? 10);
        setSyncStartYear(config.year_end);
        setSyncEndYear(config.year_end);

        const [summary] = await Promise.all([getLakeCount(config.country)]);
        if (!cancelled) setTotalLakes(summary.total_lakes);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load configuration.');
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatesLoading(true);
    fetchLakeStates(country)
      .then((s) => { if (!cancelled) { setAvailableStates(s); setStatesLoading(false); } })
      .catch(() => { if (!cancelled) setStatesLoading(false); });
    return () => { cancelled = true; };
  }, [country]);

  // ── Lock scroll ────────────────────────────────────────────────────────
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // ── Poll progress ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!started) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let timer: any = null;
    let cancelled = false;
    const poll = async () => {
      try {
        const p = await getSyncProgress();
        if (cancelled) return;
        setProgress(p);
        if (p.status === 'done' || p.status === 'failed' || p.status === 'cancelled') {
          setSyncing(false);
          setCancelling(false);
        } else {
          timer = setTimeout(poll, 1500);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Error polling sync status.');
        setSyncing(false);
      }
    };
    void poll();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [started]);

  // ── Year validation ────────────────────────────────────────────────────
  const handleStartYearChange = (val: number) => {
    const clamped = Math.max(yearStart, Math.min(yearEnd, val));
    setSyncStartYear(clamped);
    // If range now exceeds max, push end year forward
    if (syncEndYear - clamped + 1 > maxYearRange) {
      setSyncEndYear(Math.min(yearEnd, clamped + maxYearRange - 1));
    }
    if (syncEndYear < clamped) setSyncEndYear(clamped);
  };

  const handleEndYearChange = (val: number) => {
    const clamped = Math.max(yearStart, Math.min(yearEnd, val));
    setSyncEndYear(clamped);
    if (clamped - syncStartYear + 1 > maxYearRange) {
      setSyncStartYear(Math.max(yearStart, clamped - maxYearRange + 1));
    }
    if (clamped < syncStartYear) setSyncStartYear(clamped);
  };

  const yearRangeSpan = syncEndYear - syncStartYear + 1;
  const yearRangeValid = yearRangeSpan >= 1 && yearRangeSpan <= maxYearRange;

  // ── Sync handler ───────────────────────────────────────────────────────
  const handleSync = async () => {
    if (!yearRangeValid) return;
    setError(null);
    setSyncing(true);
    setCancelling(false);
    setProgress(null);
    setStarted(false);

    const duration =
      syncStartYear === syncEndYear
        ? { mode: 'year' as const, year: syncStartYear }
        : {
            mode: 'duration' as const,
            start_year: syncStartYear,
            start_month: 1,
            end_year: syncEndYear,
            end_month: 12,
          };

    const statesToSend =
      selectedStates.length === 0 || selectedStates.length === availableStates.length
        ? undefined
        : selectedStates;

    try {
      const reply = await startSync({
        source_type: 'hydrolakes',
        country,
        duration,
        sync_mode: 'refresh',
        confirmed: true,
        states: statesToSend,
      });
      setActiveJobId(reply.job_id);
      setStarted(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start synchronization.');
      setSyncing(false);
    }
  };

  // ── Progress derived ───────────────────────────────────────────────────
  const total      = progress?.total_lakes ?? 0;
  const processed  = progress?.processed   ?? 0;
  const successCnt = progress?.success      ?? 0;
  const failedCnt  = progress?.failed       ?? 0;
  const pct        = total > 0 ? Math.round((100 * processed) / total) : 0;
  const isDone     = progress?.status === 'done';
  const isFailed   = progress?.status === 'failed';
  const isCancelled = progress?.status === 'cancelled';
  const isRunning  = progress?.status === 'running';

  const handleCancel = async () => {
    if (!started) return;
    setError(null);
    setCancelling(true);
    try {
      await cancelSync(activeJobId ?? 'global');
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
      onClick={(e) => { if (e.target === e.currentTarget && !syncing) onClose(); }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary-600/30 bg-primary-600/20">
              <RefreshCw className={clsx('h-4 w-4 text-primary-400', syncing && 'animate-spin')} />
            </div>
            <div>
              <h2 id="sync-modal-title" className="text-sm font-semibold text-slate-100">
                {started ? 'Syncing Satellite Data' : 'Sync Lake Data'}
              </h2>
              <p className="text-xs text-slate-500">
                {started ? 'Retrieving Prithvi embeddings & features' : 'Configure and start sync'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={syncing}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-700/50 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-5 py-4">
          {error && (
            <div className="flex items-start gap-2.5 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {!started ? (
            <>
              {/* Row 1: Region + Lake count */}
              <div className="grid grid-cols-2 gap-3">
                <section>
                  <p className="mb-1.5 text-xs font-semibold text-slate-300">Region</p>
                  <div className="rounded-lg border border-slate-700/60 bg-surface-800 px-3 py-2 text-sm text-slate-200">
                    {country}
                  </div>
                </section>
                <section>
                  <p className="mb-1.5 text-xs font-semibold text-slate-300">Active Lakes</p>
                  <div className="flex h-[38px] items-center gap-2 rounded-lg border border-slate-700/60 bg-surface-800 px-3 py-2 text-sm text-slate-200">
                    <Database className="h-4 w-4 text-primary-400" />
                    {totalLakes === null ? (
                      <Loader2 className="h-3 w-3 animate-spin text-slate-400" />
                    ) : (
                      <span className="font-semibold text-slate-100">{totalLakes}</span>
                    )}
                  </div>
                </section>
              </div>

              {/* States multiselect */}
              <section>
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-300">
                  <MapPin className="h-3.5 w-3.5 text-slate-400" />
                  Filter by State
                  <span className="text-slate-600 font-normal">(optional — leave blank for all)</span>
                </p>
                <StateMultiSelect
                  states={availableStates}
                  selected={selectedStates}
                  onChange={setSelectedStates}
                  loading={statesLoading}
                />
              </section>

              {/* Year range */}
              <section className="space-y-2">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
                  <Calendar className="h-3.5 w-3.5 text-slate-400" />
                  Year Range
                  <span className="ml-auto font-mono text-[10px] font-normal text-slate-500">
                    max {maxYearRange} year{maxYearRange > 1 ? 's' : ''}
                  </span>
                </p>

                <div className="grid grid-cols-2 gap-3">
                  {/* Start year */}
                  <div>
                    <label className="mb-1 block text-[11px] text-slate-500">From</label>
                    <div className="relative">
                      <select
                        value={syncStartYear}
                        onChange={(e) => handleStartYearChange(Number(e.target.value))}
                        className="w-full appearance-none rounded-lg border border-slate-700/60 bg-surface-800 px-3 py-2 pr-8 text-sm font-mono text-slate-100 outline-none transition-colors hover:border-slate-600 focus:border-primary-500 cursor-pointer"
                      >
                        {Array.from({ length: yearEnd - yearStart + 1 }, (_, i) => yearEnd - i).map((y) => (
                          <option key={y} value={y} className="bg-slate-900">{y}</option>
                        ))}
                      </select>
                      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                    </div>
                  </div>
                  {/* End year */}
                  <div>
                    <label className="mb-1 block text-[11px] text-slate-500">To</label>
                    <div className="relative">
                      <select
                        value={syncEndYear}
                        onChange={(e) => handleEndYearChange(Number(e.target.value))}
                        className="w-full appearance-none rounded-lg border border-slate-700/60 bg-surface-800 px-3 py-2 pr-8 text-sm font-mono text-slate-100 outline-none transition-colors hover:border-slate-600 focus:border-primary-500 cursor-pointer"
                      >
                        {Array.from({ length: yearEnd - yearStart + 1 }, (_, i) => yearEnd - i).map((y) => (
                          <option key={y} value={y} className="bg-slate-900">{y}</option>
                        ))}
                      </select>
                      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                    </div>
                  </div>
                </div>

                {/* Range summary bar */}
                <div className={clsx(
                  'flex items-center justify-between rounded-lg px-3 py-2 text-xs',
                  !yearRangeValid
                    ? 'border border-rose-500/40 bg-rose-500/5 text-rose-400'
                    : 'border border-slate-700/40 bg-surface-800/40 text-slate-400',
                )}>
                  <span className="font-mono">
                    {syncStartYear === syncEndYear
                      ? `Year ${syncStartYear}`
                      : `${syncStartYear} – ${syncEndYear}`}
                  </span>
                  <span className={clsx(
                    'font-semibold',
                    !yearRangeValid ? 'text-rose-400' : 'text-primary-400',
                  )}>
                    {yearRangeSpan} year{yearRangeSpan > 1 ? 's' : ''}
                    {!yearRangeValid && ` (max ${maxYearRange})`}
                  </span>
                </div>
              </section>

              {/* Info note */}
              <p className="rounded-lg border border-slate-800 bg-surface-800/30 p-3 text-xs leading-relaxed text-slate-400">
                Lakes are divided into 1km × 1km cells. Cells with ≥ 15% lake coverage are processed one by one — querying GEE for Sentinel-2 composites and running the Prithvi model for embeddings & ecosystem classification.
              </p>
            </>
          ) : (
            /* Phase B: Live Progress */
            <div className="space-y-4 py-1">
              {progress === null && (
                <div className="flex flex-col items-center justify-center py-8 gap-3 text-slate-400">
                  <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
                  <p className="text-xs">Starting sync pipeline...</p>
                </div>
              )}

              {progress !== null && (
                <div className="space-y-4">
                  <div className={clsx(
                    'rounded-xl border p-3.5 flex items-start gap-3',
                    isDone && failedCnt === 0 && 'border-emerald-500/30 bg-emerald-500/5 text-emerald-300',
                    isDone && failedCnt > 0 && 'border-amber-500/30 bg-amber-500/5 text-amber-300',
                    isFailed && 'border-rose-500/30 bg-rose-500/5 text-rose-300',
                    isCancelled && 'border-slate-500/30 bg-slate-500/5 text-slate-300',
                    isRunning && 'border-primary-500/30 bg-primary-500/5 text-slate-200',
                    progress.status === 'idle' && 'border-slate-700/60 bg-surface-800 text-slate-400',
                  )}>
                    {isDone && failedCnt === 0 ? (
                      <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
                    ) : isDone && failedCnt > 0 ? (
                      <AlertCircle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
                    ) : isFailed ? (
                      <AlertCircle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
                    ) : (
                      <Loader2 className="h-5 w-5 text-primary-400 shrink-0 mt-0.5 animate-spin" />
                    )}
                    <div className="min-w-0 space-y-0.5">
                      <p className="text-xs font-semibold">
                        {isDone && failedCnt === 0 && 'Sync Complete'}
                        {isDone && failedCnt > 0 && `Sync Finished — ${failedCnt} cell(s) failed`}
                        {isFailed && 'Sync Failed'}
                        {isCancelled && 'Sync Cancelled'}
                        {isRunning && 'Processing Lakes...'}
                      </p>
                      <p className="truncate text-[11px] leading-relaxed text-slate-400">
                        {isDone && 'Prithvi embeddings & features have been updated.'}
                        {isFailed && 'The sync pipeline encountered a fatal error.'}
                        {isCancelled && 'The sync pipeline was cancelled before completion.'}
                        {isRunning && progress.current_lake && (
                          <>
                            Lake <span className="font-mono text-primary-400">{progress.current_lake}</span>
                            {progress.current_year && <> — <span className="font-mono">{progress.current_year}</span></>}
                          </>
                        )}
                        {isRunning && !progress.current_lake && 'Preparing next lake cell...'}
                      </p>
                    </div>
                  </div>

                  {total > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-1.5 text-slate-400 font-medium">
                          <Layers className="h-3.5 w-3.5" />
                          {processed} / {total} lake-cells
                        </span>
                        <span className="font-mono font-bold text-primary-400">{pct}%</span>
                      </div>
                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800/80 border border-slate-700/20">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-primary-600 via-primary-500 to-primary-400 transition-all duration-500 ease-out"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="flex flex-wrap gap-2 pt-1">
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                          {successCnt} Succeeded
                        </span>
                        {failedCnt > 0 && (
                          <span className="inline-flex items-center gap-1.5 rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium text-rose-400">
                            <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                            {failedCnt} Failed
                          </span>
                        )}
                        {isRunning && (
                          <span className="inline-flex items-center gap-1.5 rounded-md border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-400 animate-pulse">
                            <span className="h-1.5 w-1.5 animate-ping rounded-full bg-sky-400" />
                            {total - processed} Remaining
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {progress.errors.length > 0 && (
                    <details className="rounded-lg border border-rose-500/20 bg-rose-500/5">
                      <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium text-rose-400">
                        {progress.errors.length} error{progress.errors.length > 1 ? 's' : ''} — click to expand
                      </summary>
                      <ul className="max-h-28 overflow-y-auto px-3 pb-3 pt-1 space-y-1">
                        {progress.errors.map((e, idx) => (
                          <li key={idx} className="truncate font-mono text-[10px] text-rose-300/70">{e}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-slate-700/60 px-5 py-3">
          {!started ? (
            <>
              <button
                type="button"
                onClick={onClose}
                disabled={syncing}
                className="rounded-lg px-4 py-2 text-xs text-slate-400 transition-colors hover:bg-slate-700/50 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                type="button"
                id="sync-data-btn"
                onClick={handleSync}
                disabled={syncing || totalLakes === null || !yearRangeValid}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold transition-colors',
                  syncing || totalLakes === null || !yearRangeValid
                    ? 'cursor-not-allowed bg-slate-700 text-slate-400'
                    : 'bg-primary-600 text-white hover:bg-primary-500',
                )}
              >
                {syncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                {syncing ? 'Starting...' : 'Sync Data'}
              </button>
            </>
          ) : (
            <>
              {(!isDone && !isFailed && !isCancelled) && (
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={syncing || cancelling}
                  className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-700/50 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {cancelling ? 'Cancelling...' : 'Cancel Sync'}
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                disabled={syncing || cancelling}
                className={clsx(
                  'rounded-lg px-5 py-2 text-xs font-semibold transition-colors',
                  syncing || cancelling
                    ? 'cursor-not-allowed bg-slate-800 text-slate-500'
                    : 'bg-primary-600 text-white hover:bg-primary-500',
                )}
              >
                {syncing || cancelling ? 'Working...' : isCancelled ? 'Close' : isDone || isFailed ? 'Close' : 'Done'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
