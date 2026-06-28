import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Clock,
  Database,
  HardDrive,
  Info,
  Loader2,
  RefreshCw,
  ShieldAlert,
  XCircle,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import {
  fetchStates,
  getJobStatus,
  startSync,
  type IndiaState,
  type JobStatusResponse,
  type OverallStatus,
  type SyncDuration,
  type SyncJobResponse,
  type SyncMode,
  type TaskItem,
  type TaskStatus,
} from '@/api/sync';

// ── Constants ─────────────────────────────────────────────────────────────────
const MAX_STATES = 3;
const DEFAULT_YEAR_START = 2017;
const DEFAULT_YEAR_END = 2025;
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// ── Sub-components ────────────────────────────────────────────────────────────

function Tag({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-primary-600/25 border border-primary-600/40 px-2 py-0.5 text-xs text-primary-300">
      {label}
      <button
        type="button"
        onClick={onRemove}
        className="rounded hover:text-primary-100 transition-colors"
        aria-label={`Remove ${label}`}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  value: string | number;
  onChange: (v: string) => void;
  options: Array<{ value: string | number; label: string }>;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={clsx(
          'w-full appearance-none rounded-lg bg-surface-700 border border-slate-600/60',
          'px-3 py-2 pr-8 text-sm text-slate-200 focus:outline-none focus:ring-1',
          'focus:ring-primary-500 focus:border-primary-500 transition-colors',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        )}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
    </div>
  );
}

// ── Main Modal ────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 4_000;
const TERMINAL_STATUSES: OverallStatus[] = ['success', 'failed', 'partial'];

interface SyncModalProps {
  onClose: () => void;
}

type Step = 'configure' | 'confirm' | 'result';

export default function SyncModal({ onClose }: SyncModalProps) {
  // ── Remote state ─────────────────────────────────────────────
  const [allStates, setAllStates] = useState<IndiaState[]>([]);
  const [yearStart, setYearStart] = useState(DEFAULT_YEAR_START);
  const [yearEnd, setYearEnd] = useState(DEFAULT_YEAR_END);
  const [loadingStates, setLoadingStates] = useState(true);
  const [stateLoadError, setStateLoadError] = useState<string | null>(null);

  // ── Form state ────────────────────────────────────────────────
  const [selectedStates, setSelectedStates]   = useState<string[]>([]);
  const [stateSearch, setStateSearch]         = useState('');
  const [showDropdown, setShowDropdown]       = useState(false);

  const [durMode, setDurMode]         = useState<'year' | 'duration'>('year');
  const [singleYear, setSingleYear]   = useState<number>(DEFAULT_YEAR_END);
  const [startYear, setStartYear]     = useState<number>(DEFAULT_YEAR_END - 1);
  const [startMonth, setStartMonth]   = useState<number>(1);
  const [endYear, setEndYear]         = useState<number>(DEFAULT_YEAR_END);
  const [endMonth, setEndMonth]       = useState<number>(12);

  const [syncMode, setSyncMode] = useState<SyncMode>('wipe');

  // ── Step state ────────────────────────────────────────────────
  const [step, setStep]             = useState<Step>('configure');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult]         = useState<SyncJobResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ── Polling state ─────────────────────────────────────────────
  const [jobStatus, setJobStatus]   = useState<JobStatusResponse | null>(null);
  const [pollError, setPollError]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);

  // ── Load states from backend ──────────────────────────────────
  useEffect(() => {
    fetchStates()
      .then((res) => {
        setAllStates(res.states);
        setYearStart(res.year_start);
        setYearEnd(res.year_end);
        setSingleYear(res.year_end);
        setStartYear(Math.max(res.year_start, res.year_end - 1));
        setEndYear(res.year_end);
      })
      .catch(() => setStateLoadError('Could not load state list from server.'))
      .finally(() => setLoadingStates(false));
  }, []);

  // ── Close dropdown on outside click ──────────────────────────
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // ── Lock body scroll while modal is open ─────────────────────
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // ── Close on Escape ──────────────────────────────────────────
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  // ── Start polling when result step is entered ─────────────────
  useEffect(() => {
    if (step !== 'result' || !result) return;

    const poll = () => {
      getJobStatus(result.job_id)
        .then((s) => {
          setJobStatus(s);
          setPollError(null);
          if (TERMINAL_STATUSES.includes(s.overall) && pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        })
        .catch((err: Error) => setPollError(err.message));
    };

    poll(); // immediate first fetch
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [step, result]);

  // ── Helpers ───────────────────────────────────────────────────
  const filteredStates = allStates.filter(
    (s) =>
      s.name.toLowerCase().includes(stateSearch.toLowerCase()) &&
      !selectedStates.includes(s.name),
  );

  const addState = (name: string) => {
    if (selectedStates.length >= MAX_STATES) return;
    setSelectedStates((prev) => [...prev, name]);
    setStateSearch('');
    setShowDropdown(false);
  };

  const removeState = (name: string) => {
    setSelectedStates((prev) => prev.filter((s) => s !== name));
  };

  const buildDuration = (): SyncDuration =>
    durMode === 'year'
      ? { mode: 'year', year: singleYear }
      : { mode: 'duration', start_year: startYear, start_month: startMonth, end_year: endYear, end_month: endMonth };

  const previewYears = (): number[] => {
    if (durMode === 'year') return [singleYear];
    const years: number[] = [];
    for (let y = startYear; y <= endYear; y++) years.push(y);
    return years;
  };

  const totalTasks = selectedStates.length * previewYears().length;
  const canProceed = selectedStates.length > 0 && (durMode === 'year' || startYear <= endYear);

  // ── Submit ────────────────────────────────────────────────────
  const handleConfirmSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await startSync({
        states:    selectedStates,
        duration:  buildDuration(),
        sync_mode: syncMode,
        confirmed: true,
      });
      setResult(res);
      setStep('result');
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Year / Month option arrays ────────────────────────────────
  const yearOptions = Array.from(
    { length: yearEnd - yearStart + 1 },
    (_, i) => ({ value: yearStart + i, label: String(yearStart + i) }),
  );
  const monthOptions = MONTHS.map((m, i) => ({ value: i + 1, label: m }));

  // ── Render (portal keeps modal above Leaflet map panes) ───────
  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-modal-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative w-full max-w-lg rounded-2xl bg-surface-900 border border-slate-700/60 shadow-2xl flex flex-col max-h-[90vh]">

        {/* ── Header ──────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600/20 border border-primary-600/30">
              <RefreshCw className="h-4 w-4 text-primary-400" />
            </div>
            <div>
              <h2 id="sync-modal-title" className="text-sm font-semibold text-slate-100">Sync Data</h2>
              <p className="text-xs text-slate-500">Trigger ML pipeline for selected states</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Body ─────────────────────────────────────────────── */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-5">

          {/* ══ STEP 1: CONFIGURE ══════════════════════════════ */}
          {step === 'configure' && (
            <>
              {/* State selector */}
              <section>
                <label className="mb-1.5 block text-xs font-medium text-slate-300">
                  States / Union Territories
                  <span className="ml-1.5 text-slate-500">(max {MAX_STATES})</span>
                </label>

                {/* Selected tags */}
                {selectedStates.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {selectedStates.map((s) => (
                      <Tag key={s} label={s} onRemove={() => removeState(s)} />
                    ))}
                  </div>
                )}

                {/* Dropdown */}
                <div className="relative" ref={dropdownRef}>
                  <input
                    type="text"
                    value={stateSearch}
                    onChange={(e) => { setStateSearch(e.target.value); setShowDropdown(true); }}
                    onFocus={() => setShowDropdown(true)}
                    placeholder={
                      selectedStates.length >= MAX_STATES
                        ? `Maximum ${MAX_STATES} states selected`
                        : 'Search and select a state…'
                    }
                    disabled={selectedStates.length >= MAX_STATES || loadingStates}
                    className={clsx(
                      'w-full rounded-lg bg-surface-700 border border-slate-600/60 px-3 py-2',
                      'text-sm text-slate-200 placeholder:text-slate-500',
                      'focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                    )}
                  />
                  {showDropdown && filteredStates.length > 0 && (
                    <ul className="absolute z-20 mt-1 max-h-52 w-full overflow-y-auto rounded-lg bg-surface-800 border border-slate-700/60 shadow-xl">
                      {filteredStates.map((s) => (
                        <li key={s.name}>
                          <button
                            type="button"
                            onClick={() => addState(s.name)}
                            className="w-full px-3 py-2 text-left text-sm text-slate-300 hover:bg-primary-600/20 hover:text-primary-300 transition-colors"
                          >
                            {s.name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                {stateLoadError && (
                  <p className="mt-1 text-xs text-red-400">{stateLoadError}</p>
                )}
              </section>

              {/* Duration selector */}
              <section>
                <label className="mb-1.5 block text-xs font-medium text-slate-300">
                  Time Range
                </label>
                <div className="mb-3 flex rounded-lg overflow-hidden border border-slate-700/60">
                  {(['year', 'duration'] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setDurMode(m)}
                      className={clsx(
                        'flex-1 py-1.5 text-xs font-medium transition-colors',
                        durMode === m
                          ? 'bg-primary-600/30 text-primary-300'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/40',
                      )}
                    >
                      {m === 'year' ? 'Single Year' : 'Date Range'}
                    </button>
                  ))}
                </div>

                {durMode === 'year' ? (
                  <Select
                    value={singleYear}
                    onChange={(v) => setSingleYear(Number(v))}
                    options={yearOptions}
                  />
                ) : (
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <p className="mb-1 text-xs text-slate-500">Start Month</p>
                        <Select
                          value={startMonth}
                          onChange={(v) => setStartMonth(Number(v))}
                          options={monthOptions}
                        />
                      </div>
                      <div>
                        <p className="mb-1 text-xs text-slate-500">Start Year</p>
                        <Select
                          value={startYear}
                          onChange={(v) => setStartYear(Number(v))}
                          options={yearOptions}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <p className="mb-1 text-xs text-slate-500">End Month</p>
                        <Select
                          value={endMonth}
                          onChange={(v) => setEndMonth(Number(v))}
                          options={monthOptions}
                        />
                      </div>
                      <div>
                        <p className="mb-1 text-xs text-slate-500">End Year</p>
                        <Select
                          value={endYear}
                          onChange={(v) => setEndYear(Number(v))}
                          options={yearOptions.filter((y) => Number(y.value) >= startYear)}
                        />
                      </div>
                    </div>
                    {startYear > endYear && (
                      <p className="text-xs text-amber-400">End year must be ≥ start year.</p>
                    )}
                  </div>
                )}
              </section>

              {/* Sync mode */}
              <section>
                <label className="mb-1.5 block text-xs font-medium text-slate-300">
                  Before Sync
                </label>
                <div className="space-y-2">
                  {(
                    [
                      {
                        value: 'wipe' as SyncMode,
                        icon: <Database className="h-4 w-4" />,
                        title: 'Wipe & Re-ingest',
                        desc:  'Delete existing data for selected states then run fresh.',
                      },
                      {
                        value: 'backup' as SyncMode,
                        icon: <HardDrive className="h-4 w-4" />,
                        title: 'Backup then Wipe',
                        desc:  'pg_dump to /app/backups/ before deleting. Safer but slower.',
                      },
                    ] as const
                  ).map((opt) => (
                    <label
                      key={opt.value}
                      className={clsx(
                        'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                        syncMode === opt.value
                          ? 'border-primary-500/50 bg-primary-600/10'
                          : 'border-slate-700/60 bg-surface-800 hover:border-slate-600',
                      )}
                    >
                      <input
                        type="radio"
                        name="syncMode"
                        value={opt.value}
                        checked={syncMode === opt.value}
                        onChange={() => setSyncMode(opt.value)}
                        className="sr-only"
                      />
                      <span
                        className={clsx(
                          'mt-0.5',
                          syncMode === opt.value ? 'text-primary-400' : 'text-slate-400',
                        )}
                      >
                        {opt.icon}
                      </span>
                      <div>
                        <p className="text-xs font-medium text-slate-200">{opt.title}</p>
                        <p className="text-xs text-slate-500">{opt.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </section>

              {/* Summary chip */}
              {canProceed && (
                <div className="flex items-center gap-2 rounded-lg bg-slate-800/60 border border-slate-700/40 px-3 py-2">
                  <Info className="h-3.5 w-3.5 flex-shrink-0 text-slate-400" />
                  <p className="text-xs text-slate-400">
                    <span className="text-slate-200">{selectedStates.length}</span> state(s) ×{' '}
                    <span className="text-slate-200">{previewYears().length}</span> year(s) ={' '}
                    <span className="text-primary-300">{totalTasks}</span> pipeline task(s)
                  </p>
                </div>
              )}
            </>
          )}

          {/* ══ STEP 2: CONFIRM WARNING ═══════════════════════ */}
          {step === 'confirm' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
                <ShieldAlert className="h-5 w-5 flex-shrink-0 text-amber-400 mt-0.5" />
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-amber-300">
                    Warning — Existing Data Will Be Deleted
                  </p>
                  <p className="text-xs text-amber-200/80 leading-relaxed">
                    All stored features, embeddings, and temporal profiles for the
                    following state(s) will be permanently removed before the new
                    ingestion run starts:
                  </p>
                  <ul className="ml-3 list-disc space-y-0.5">
                    {selectedStates.map((s) => (
                      <li key={s} className="text-xs text-amber-200">
                        {s}
                      </li>
                    ))}
                  </ul>
                  {syncMode === 'backup' ? (
                    <p className="text-xs text-emerald-400 flex items-center gap-1.5">
                      <HardDrive className="h-3 w-3" />
                      A database backup will be created first at{' '}
                      <code className="rounded bg-black/30 px-1">/app/backups/</code>
                    </p>
                  ) : (
                    <p className="text-xs text-red-400 flex items-center gap-1.5">
                      <AlertTriangle className="h-3 w-3" />
                      No backup will be made. This action cannot be undone.
                    </p>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-slate-700/40 bg-surface-800 px-4 py-3 space-y-1">
                <p className="text-xs text-slate-400">Pipeline summary</p>
                <p className="text-sm text-slate-200">
                  <span className="font-medium text-primary-300">{totalTasks}</span> tasks for{' '}
                  {selectedStates.join(', ')} — years{' '}
                  {previewYears()[0]}–{previewYears().at(-1)}
                </p>
              </div>

              {submitError && (
                <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  {submitError}
                </p>
              )}
            </div>
          )}

          {/* ══ STEP 3: LIVE STATUS ══════════════════════════ */}
          {step === 'result' && result && (
            <div className="space-y-4">
              {/* Header summary */}
              <JobStatusHeader result={result} status={jobStatus} />

              {/* Progress bar */}
              {jobStatus && (
                <ProgressBar
                  total={jobStatus.total}
                  counts={jobStatus.counts}
                  overall={jobStatus.overall}
                />
              )}

              {/* Per-task list */}
              {jobStatus ? (
                <TaskList tasks={jobStatus.tasks} />
              ) : (
                <div className="flex items-center justify-center gap-2 py-6 text-slate-500">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-xs">Fetching task status…</span>
                </div>
              )}

              {pollError && (
                <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  Status poll error: {pollError}
                </p>
              )}

              <p className="text-xs text-slate-500 text-center">
                Also available in{' '}
                <a
                  href="http://localhost:5555"
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary-400 underline underline-offset-2 hover:text-primary-300"
                >
                  Flower
                </a>{' '}
                · Job{' '}
                <span className="font-mono text-slate-400">{result.job_id.slice(0, 8)}…</span>
              </p>
            </div>
          )}
        </div>

        {/* ── Footer ───────────────────────────────────────────── */}
        <div className="border-t border-slate-700/60 px-5 py-3 flex items-center justify-end gap-2">
          {step === 'configure' && (
            <>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-xs text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => setStep('confirm')}
                disabled={!canProceed}
                className={clsx(
                  'rounded-lg px-4 py-2 text-xs font-medium transition-colors',
                  canProceed
                    ? 'bg-primary-600 text-white hover:bg-primary-500'
                    : 'bg-slate-700 text-slate-500 cursor-not-allowed',
                )}
              >
                Continue
              </button>
            </>
          )}

          {step === 'confirm' && (
            <>
              <button
                type="button"
                onClick={() => { setStep('configure'); setSubmitError(null); }}
                disabled={submitting}
                className="rounded-lg px-4 py-2 text-xs text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 transition-colors disabled:opacity-50"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleConfirmSubmit}
                disabled={submitting}
                className={clsx(
                  'flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
                  'bg-amber-600 text-white hover:bg-amber-500 disabled:opacity-60 disabled:cursor-not-allowed',
                )}
              >
                {submitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <AlertTriangle className="h-3.5 w-3.5" />
                )}
                {submitting ? 'Starting…' : 'I understand — Start Sync'}
              </button>
            </>
          )}

          {step === 'result' && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-xs font-medium bg-primary-600 text-white hover:bg-primary-500 transition-colors"
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ── Status sub-components ─────────────────────────────────────────────────────

const OVERALL_LABEL: Record<OverallStatus, string> = {
  pending: 'Queued — waiting for workers',
  running: 'Running…',
  success: 'All tasks completed',
  failed:  'All tasks failed',
  partial: 'Completed with errors',
};

const OVERALL_COLOR: Record<OverallStatus, string> = {
  pending: 'text-slate-400',
  running: 'text-primary-300',
  success: 'text-emerald-400',
  failed:  'text-red-400',
  partial: 'text-amber-400',
};

function JobStatusHeader({
  result,
  status,
}: {
  result: SyncJobResponse;
  status: JobStatusResponse | null;
}) {
  const overall: OverallStatus = status?.overall ?? 'pending';
  return (
    <div className="flex items-center gap-3">
      <div
        className={clsx(
          'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border',
          overall === 'success'
            ? 'border-emerald-500/40 bg-emerald-500/10'
            : overall === 'failed'
            ? 'border-red-500/40 bg-red-500/10'
            : overall === 'partial'
            ? 'border-amber-500/40 bg-amber-500/10'
            : 'border-primary-600/30 bg-primary-600/20',
        )}
      >
        {overall === 'success' ? (
          <CheckCircle2 className="h-5 w-5 text-emerald-400" />
        ) : overall === 'failed' ? (
          <XCircle className="h-5 w-5 text-red-400" />
        ) : overall === 'partial' ? (
          <AlertTriangle className="h-5 w-5 text-amber-400" />
        ) : (
          <RefreshCw className={clsx('h-5 w-5 text-primary-400', overall === 'running' && 'animate-spin')} />
        )}
      </div>
      <div>
        <p className={clsx('text-sm font-semibold', OVERALL_COLOR[overall])}>
          {OVERALL_LABEL[overall]}
        </p>
        <p className="text-xs text-slate-500">
          {result.states.join(', ')} · {result.years[0]}–{result.years.at(-1)} ·{' '}
          {result.tasks_dispatched} tasks
        </p>
      </div>
    </div>
  );
}

function ProgressBar({
  total,
  counts,
  overall,
}: {
  total: number;
  counts: JobStatusResponse['counts'];
  overall: OverallStatus;
}) {
  if (total === 0) return null;
  const pct = (n: number) => `${Math.round((n / total) * 100)}%`;

  return (
    <div className="space-y-1.5">
      {/* Segmented bar */}
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-700/60">
        {counts.success > 0 && (
          <div
            className="h-full bg-emerald-500 transition-all duration-500"
            style={{ width: pct(counts.success) }}
          />
        )}
        {counts.running > 0 && (
          <div
            className="h-full bg-primary-500 animate-pulse transition-all duration-500"
            style={{ width: pct(counts.running) }}
          />
        )}
        {counts.failed > 0 && (
          <div
            className="h-full bg-red-500 transition-all duration-500"
            style={{ width: pct(counts.failed) }}
          />
        )}
      </div>
      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-slate-400">
        <LegendDot color="bg-emerald-500" label={`${counts.success} done`} />
        <LegendDot color="bg-primary-500" label={`${counts.running} running`} />
        <LegendDot color="bg-slate-600"   label={`${counts.pending} pending`} />
        {counts.failed > 0 && (
          <LegendDot color="bg-red-500" label={`${counts.failed} failed`} />
        )}
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={clsx('h-1.5 w-1.5 rounded-full', color)} />
      {label}
    </span>
  );
}

const STATUS_ICON: Record<TaskStatus, React.ReactNode> = {
  pending: <Clock    className="h-3.5 w-3.5 text-slate-500" />,
  running: <CircleDot className="h-3.5 w-3.5 text-primary-400 animate-pulse" />,
  success: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />,
  failed:  <XCircle  className="h-3.5 w-3.5 text-red-400" />,
};

const STATUS_ROW_BG: Record<TaskStatus, string> = {
  pending: '',
  running: 'bg-primary-600/5',
  success: 'bg-emerald-500/5',
  failed:  'bg-red-500/5',
};

function TaskList({ tasks }: { tasks: TaskItem[] }) {
  if (tasks.length === 0) return null;

  // Group by state for cleaner display
  const byState = tasks.reduce<Record<string, TaskItem[]>>((acc, t) => {
    (acc[t.state] ??= []).push(t);
    return acc;
  }, {});

  return (
    <div className="space-y-3 max-h-52 overflow-y-auto pr-1">
      {Object.entries(byState).map(([state, items]) => (
        <div key={state}>
          <p className="mb-1 text-xs font-medium text-slate-400">{state}</p>
          <div className="rounded-lg border border-slate-700/40 overflow-hidden divide-y divide-slate-700/40">
            {items.map((t) => (
              <div
                key={t.task_id}
                className={clsx(
                  'flex items-center justify-between px-3 py-1.5 text-xs',
                  STATUS_ROW_BG[t.status],
                )}
              >
                <div className="flex items-center gap-2">
                  {STATUS_ICON[t.status]}
                  <span className="text-slate-300">Year {t.year}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={clsx(
                      'capitalize',
                      t.status === 'success' ? 'text-emerald-400'
                        : t.status === 'failed'  ? 'text-red-400'
                        : t.status === 'running' ? 'text-primary-400'
                        : 'text-slate-500',
                    )}
                  >
                    {t.status}
                  </span>
                  {t.error && (
                    <span
                      className="max-w-[140px] truncate text-red-400/80"
                      title={t.error}
                    >
                      {t.error}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

