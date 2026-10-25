import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Image,
  Loader2,
  X,
  XCircle,
  CheckCircle2,
  AlertTriangle,
  Satellite,
  HardDrive,
  FolderOpen,
} from 'lucide-react';
import { clsx } from 'clsx';

import {
  startFetchImages,
  getImageryProgress,
  getImageryStorage,
  checkImageryStorage,
  cancelImageryFetch,
  type FetchImagesResponse,
  type ImageryProgress,
  type StorageCheck,
  type StorageInfo,
  type StorageLocation,
} from '@/api/imagery';

interface FetchImagesModalProps {
  onClose: () => void;
}

const CURRENT_YEAR = 2025;
const YEAR_OPTIONS = Array.from({ length: 10 }, (_, i) => CURRENT_YEAR - i);
const POLL_MS = 2000;
const MAX_POLL_FAILURES = 3;

/** Bands in the downloaded GeoTIFF, in file order (S2_BANDS_DOWNLOAD). */
const BANDS: { id: string; name: string; prithvi?: boolean }[] = [
  { id: 'B1', name: 'Coastal aerosol · 443 nm' },
  { id: 'B2', name: 'Blue · 490 nm', prithvi: true },
  { id: 'B3', name: 'Green · 560 nm', prithvi: true },
  { id: 'B4', name: 'Red · 665 nm', prithvi: true },
  { id: 'B5', name: 'Red edge 1 · 705 nm' },
  { id: 'B6', name: 'Red edge 2 · 740 nm' },
  { id: 'B7', name: 'Red edge 3 · 783 nm' },
  { id: 'B8', name: 'NIR broad · 842 nm' },
  { id: 'B8A', name: 'NIR narrow · 865 nm', prithvi: true },
  { id: 'B11', name: 'SWIR 1 · 1610 nm', prithvi: true },
  { id: 'B12', name: 'SWIR 2 · 2190 nm', prithvi: true },
  { id: 'CLEAR_COUNT', name: 'Clear observations per pixel' },
];

const ACTIVE_STATUSES: ImageryProgress['status'][] = ['running', 'cancelling'];

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export default function FetchImagesModal({ onClose }: FetchImagesModalProps) {
  const [selectedYears, setSelectedYears] = useState<number[]>([CURRENT_YEAR - 1]);
  const [starting, setStarting] = useState(false);
  const [result, setResult] = useState<FetchImagesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ImageryProgress | null>(null);
  const [pollWarning, setPollWarning] = useState<string | null>(null);

  // Storage location per year: SENTINEL_DATA_DIR unless changed here
  // (``assign``). Existing images are listed from the paths in lake_images.
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [assign, setAssign] = useState<Record<number, string>>({});
  // Folder picked under "Set all selected years to". Applies to every selected
  // year — also years ticked afterwards — unless a year has its own choice.
  const [allTarget, setAllTarget] = useState<string | null>(null);
  const [customPath, setCustomPath] = useState<string>('');
  const [customCheck, setCustomCheck] = useState<StorageCheck | null>(null);
  const [customOptions, setCustomOptions] = useState<StorageLocation[]>([]);
  const [checking, setChecking] = useState(false);

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollFailuresRef = useRef(0);
  const mountedRef = useRef(true);

  // Prevent body scroll when modal is open
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) clearTimeout(pollRef.current);
    pollRef.current = null;
  }, []);

  // Chained timeouts (not setInterval) so slow responses never overlap.
  const poll = useCallback(async () => {
    try {
      const p = await getImageryProgress();
      if (!mountedRef.current) return;
      pollFailuresRef.current = 0;
      setPollWarning(null);
      setProgress(p);
      if (!ACTIVE_STATUSES.includes(p.status)) {
        stopPolling();
        return;
      }
    } catch {
      if (!mountedRef.current) return;
      pollFailuresRef.current += 1;
      if (pollFailuresRef.current >= MAX_POLL_FAILURES) {
        setPollWarning('Lost connection to the backend — still retrying…');
      }
    }
    pollRef.current = setTimeout(poll, POLL_MS);
  }, [stopPolling]);

  const startPolling = useCallback(() => {
    stopPolling();
    pollFailuresRef.current = 0;
    void poll();
  }, [poll, stopPolling]);

  // On open: load storage info and pick up a run that is already going
  useEffect(() => {
    mountedRef.current = true;

    getImageryStorage()
      .then((info) => {
        if (mountedRef.current) setStorage(info);
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          setStorageError(err instanceof Error ? err.message : 'Failed to load storage info.');
        }
      });

    getImageryProgress()
      .then((p) => {
        if (!mountedRef.current) return;
        setProgress(p.status === 'idle' ? null : p);
        if (ACTIVE_STATUSES.includes(p.status)) startPolling();
      })
      .catch(() => {});

    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [startPolling, stopPolling]);

  const toggleYear = (year: number) => {
    setSelectedYears((prev) =>
      prev.includes(year) ? prev.filter((y) => y !== year) : [...prev, year].sort((a, b) => a - b),
    );
  };

  const runCustomCheck = async (path: string) => {
    if (!path.trim()) {
      setCustomCheck(null);
      return;
    }
    setChecking(true);
    try {
      const res = await checkImageryStorage(path.trim());
      if (!mountedRef.current) return;
      setCustomCheck(res);
      if (res.valid && res.free_bytes != null && res.total_bytes != null) {
        const option: StorageLocation = {
          path: res.path,
          label: 'Custom folder',
          free_bytes: res.free_bytes,
          total_bytes: res.total_bytes,
        };
        setCustomOptions((prev) => [...prev.filter((o) => o.path !== res.path), option]);
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        setCustomCheck({
          path,
          valid: false,
          error: err instanceof Error ? err.message : 'Check failed.',
          free_bytes: null,
          total_bytes: null,
        });
      }
    } finally {
      if (mountedRef.current) setChecking(false);
    }
  };

  // Every folder the user can pick: drives, folders already in use, custom
  const options = useMemo(() => {
    const map = new Map<string, StorageLocation>();
    storage?.suggestions.forEach((o) => map.set(o.path, o));
    storage?.years.forEach((y) =>
      y.roots.forEach((r) => {
        if (!map.has(r.root) && r.free_bytes != null && r.total_bytes != null) {
          map.set(r.root, {
            path: r.root,
            label: 'Folder in use',
            free_bytes: r.free_bytes,
            total_bytes: r.total_bytes,
          });
        }
      }),
    );
    customOptions.forEach((o) => map.set(o.path, o));
    return map;
  }, [storage, customOptions]);

  const currentRoot = useCallback(
    (year: number) => storage?.years.find((y) => y.year === year)?.data_root ?? '',
    [storage],
  );
  const targetFor = useCallback(
    (year: number) => assign[year] ?? allTarget ?? currentRoot(year),
    [assign, allTarget, currentRoot],
  );

  const assignAll = (path: string) => {
    setAllTarget(path);
    setAssign({});
  };

  // Space needed per drive: merged image + tiles (≈ 2×), upper bound — lakes
  // already in the current format are skipped. Drives are told apart by size.
  const driveNeeds = useMemo(() => {
    if (!storage) return [];
    const drives = new Map<
      string,
      { paths: Set<string>; years: number[]; need: number; free: number | null }
    >();
    selectedYears.forEach((year) => {
      const path = targetFor(year);
      const opt = options.get(path);
      const key = opt ? `${opt.total_bytes}:${opt.free_bytes}` : path;
      const need = storage.estimated_bytes_per_year * 2;
      const entry = drives.get(key) ?? {
        paths: new Set<string>(),
        years: [],
        need: 0,
        free: opt?.free_bytes ?? null,
      };
      entry.paths.add(path);
      entry.years.push(year);
      entry.need += need;
      drives.set(key, entry);
    });
    return [...drives.values()].map((d) => ({
      ...d,
      low: d.free != null && d.free < d.need,
    }));
  }, [storage, selectedYears, targetFor, options]);
  const lowSpace = driveNeeds.some((d) => d.low);

  // Only send years whose folder actually changes
  const yearRootsToSend = useMemo(() => {
    const out: Record<number, string> = {};
    selectedYears.forEach((y) => {
      const target = targetFor(y);
      if (target && target !== currentRoot(y)) out[y] = target;
    });
    return out;
  }, [selectedYears, targetFor, currentRoot]);

  const isActive = progress != null && ACTIVE_STATUSES.includes(progress.status);
  const isRunning = starting || isActive;
  const isCancelling = progress?.status === 'cancelling';
  const isDone = progress?.status === 'done';
  const isFailed = progress?.status === 'failed';
  const isCancelled = progress?.status === 'cancelled';

  const canStart = selectedYears.length > 0 && !isRunning;

  const handleFetch = async () => {
    if (selectedYears.length === 0) {
      setError('Please select at least one year.');
      return;
    }

    setStarting(true);
    setError(null);
    setResult(null);
    setProgress(null);

    try {
      const res = await startFetchImages({
        lake_ids: null, // all active lakes
        years: selectedYears,
        confirmed: true,
        year_roots: Object.keys(yearRootsToSend).length > 0 ? yearRootsToSend : null,
      });
      setResult(res);
      setAssign({});
      setAllTarget(null);
      // Reload so the per-year folders show the saved choice
      getImageryStorage()
        .then((info) => mountedRef.current && setStorage(info))
        .catch(() => {});
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start image download.');
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    try {
      await cancelImageryFetch();
      // Keep polling: the status goes cancelling → cancelled once
      // in-flight tiles have finished.
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel.');
    }
  };

  const progressPercent =
    progress && progress.total > 0
      ? Math.min(100, Math.round((progress.processed / progress.total) * 100))
      : 0;

  const statusLabel = (() => {
    if (!progress) return '';
    if (isCancelling) return 'Cancelling — finishing tiles already in progress…';
    if (isActive) {
      if (progress.total === 0) return 'Preparing lake list…';
      if (progress.current_lake_id) {
        const tile = progress.current_tile_index ? ` · tile ${progress.current_tile_index}` : '';
        return `Lake ${progress.current_lake_id} / ${progress.current_year}${tile}`;
      }
      return 'Starting downloads…';
    }
    if (isDone) return progress.failed > 0 ? 'Finished with failures' : 'Download complete';
    if (isCancelled) return 'Download cancelled';
    if (isFailed) return 'Download failed';
    return '';
  })();

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fetch-images-title"
      onClick={(event) => {
        if (event.target === event.currentTarget && !starting) onClose();
      }}
    >
      <div className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl scrollbar-thin">
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/15">
              <Satellite className="h-4 w-4 text-cyan-400" />
            </div>
            <div>
              <h2 id="fetch-images-title" className="text-sm font-semibold text-slate-100">
                Fetch Satellite Images
              </h2>
              <p className="text-xs text-slate-500">
                Download Sentinel-2 composites for all active lakes
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={starting}
            className={clsx(
              'rounded-lg p-1.5 transition-colors',
              starting
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

          {/* Storage location */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-300">
              <HardDrive className="h-3.5 w-3.5 text-slate-400" />
              Download location
            </label>

            {storageError && (
              <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-400">
                {storageError}
              </p>
            )}
            {!storage && !storageError && (
              <p className="flex items-center gap-1.5 text-[11px] text-slate-500">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading drives…
              </p>
            )}

            {storage && (
              <div className="space-y-2.5">
                {/* Apply one folder to every selected year */}
                <div>
                  <p className="mb-1.5 text-[10px] uppercase tracking-wide text-slate-500">
                    Set all selected years to
                  </p>
                  <div className="space-y-1.5">
                    {[...options.values()].map((o) => {
                      const allHere =
                        selectedYears.length > 0 &&
                        selectedYears.every((y) => targetFor(y) === o.path);
                      return (
                        <button
                          key={o.path}
                          type="button"
                          disabled={isRunning || selectedYears.length === 0}
                          onClick={() => assignAll(o.path)}
                          className={clsx(
                            'flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-1.5 text-left transition-colors',
                            allHere
                              ? 'border-cyan-500/50 bg-cyan-500/10'
                              : 'border-slate-700/60 bg-surface-800 hover:border-slate-600',
                            (isRunning || selectedYears.length === 0) &&
                              'cursor-not-allowed opacity-60',
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block text-xs text-slate-200">
                              {o.path === storage.default_root
                                ? 'Default (SENTINEL_DATA_DIR)'
                                : o.label}
                            </span>
                            <span
                              className="block truncate font-mono text-[10px] text-slate-500"
                              title={o.path}
                            >
                              {o.path}
                            </span>
                          </span>
                          <span className="shrink-0 text-[10px] font-medium text-slate-400">
                            {formatBytes(o.free_bytes)} free
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Custom path */}
                <div className="rounded-lg border border-slate-700/60 bg-surface-800 px-3 py-2">
                  <label className="flex items-center gap-1.5 text-xs text-slate-200">
                    <FolderOpen className="h-3.5 w-3.5 text-slate-400" />
                    Other folder (absolute path on the backend machine)
                  </label>
                  <div className="mt-1.5 flex gap-1.5">
                    <input
                      type="text"
                      value={customPath}
                      disabled={isRunning}
                      placeholder="/media/you/Drive/ecotwin_sentinel"
                      spellCheck={false}
                      onChange={(e) => {
                        setCustomPath(e.target.value);
                        setCustomCheck(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void runCustomCheck(customPath);
                      }}
                      className="min-w-0 flex-1 rounded-md border border-slate-700/60 bg-surface-900 px-2 py-1 font-mono text-[11px] text-slate-200 placeholder:text-slate-600 focus:border-cyan-500/60 focus:outline-none disabled:opacity-60"
                    />
                    <button
                      type="button"
                      disabled={isRunning || checking || !customPath.trim()}
                      onClick={() => void runCustomCheck(customPath)}
                      className="rounded-md border border-slate-700/60 px-2 text-[11px] text-slate-300 hover:bg-slate-700/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {checking ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Add'}
                    </button>
                  </div>
                  {customCheck && (
                    <p
                      className={clsx(
                        'mt-1 text-[10px]',
                        customCheck.valid ? 'text-emerald-400' : 'text-red-400',
                      )}
                    >
                      {customCheck.valid
                        ? `Added — ${formatBytes(customCheck.free_bytes)} free. Pick it above or per year below (created on start if missing).`
                        : customCheck.error}
                    </p>
                  )}
                </div>

                {/* Folder per selected year */}
                {selectedYears.length > 0 && (
                  <div className="rounded-lg border border-slate-700/60">
                    <div className="flex items-center justify-between border-b border-slate-700/60 px-3 py-1.5">
                      <span className="text-[10px] uppercase tracking-wide text-slate-500">
                        Folder per year
                      </span>
                      {(Object.keys(assign).length > 0 || allTarget) && !isRunning && (
                        <button
                          type="button"
                          onClick={() => {
                            setAssign({});
                            setAllTarget(null);
                          }}
                          className="text-[10px] text-slate-400 hover:text-slate-200"
                        >
                          Undo changes
                        </button>
                      )}
                    </div>
                    <ul className="divide-y divide-slate-700/40">
                      {[...selectedYears].reverse().map((year) => {
                        const target = targetFor(year);
                        const changed = target !== currentRoot(year);
                        const inUse = storage.years.find((y) => y.year === year)?.roots ?? [];
                        return (
                          <li key={year} className="px-3 py-1.5">
                            <div className="flex items-center gap-2">
                              <span className="w-10 shrink-0 font-mono text-xs text-slate-300">
                                {year}
                              </span>
                              <select
                                value={target}
                                disabled={isRunning}
                                onChange={(e) =>
                                  setAssign((prev) => ({
                                    ...prev,
                                    [year]: e.target.value,
                                  }))
                                }
                                aria-label={`Folder for ${year}`}
                                className="min-w-0 flex-1 truncate rounded-md border border-slate-700/60 bg-surface-900 px-1.5 py-1 font-mono text-[10px] text-slate-200 focus:border-cyan-500/60 focus:outline-none disabled:opacity-60"
                              >
                                {[...options.values()].map((o) => (
                                  <option key={o.path} value={o.path}>
                                    {o.path} ({formatBytes(o.free_bytes)} free)
                                  </option>
                                ))}
                              </select>
                              <span className="w-24 shrink-0 text-right text-[10px]">
                                {changed ? (
                                <span className="text-cyan-300">changed</span>
                              ) : (
                                <span className="text-slate-500">default</span>
                              )}
                              </span>
                            </div>
                            {/* Existing images of this year (from lake_images) */}
                            {inUse.length > 0 && (
                              <div className="mt-0.5 space-y-px pl-12">
                                {inUse.map((r) => (
                                  <p
                                    key={r.root}
                                    className="truncate font-mono text-[9px] text-slate-500"
                                    title={r.root}
                                  >
                                    {r.lakes} lake image
                                    {r.lakes !== 1 ? 's' : ''} in {r.root}
                                  </p>
                                ))}
                              </div>
                            )}
                            {/* Selected folder differs from where this year's images already are */}
                            {inUse.length > 0 && !inUse.some((r) => r.root === target) && (
                              <p className="mt-0.5 flex items-start gap-1 pl-12 text-[10px] text-amber-400">
                                <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
                                {year}&apos;s images are in {inUse[0].root} — new or retried tiles
                                would go to {target}. Pick that folder to keep the year together.
                              </p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                {/* Size estimate per drive */}
                {driveNeeds.length > 0 && (
                  <div className="space-y-0.5">
                    {driveNeeds.map((d) => (
                      <p
                        key={[...d.paths].join('|')}
                        className={clsx(
                          'text-[10px] leading-relaxed',
                          d.low ? 'text-amber-400' : 'text-slate-500',
                        )}
                      >
                        {d.low && <AlertTriangle className="mr-1 inline h-3 w-3 align-[-2px]" />}
                        {[...d.paths].join(', ')} — {[...d.years].sort((a, b) => a - b).join(', ')}:
                        needs up to {formatBytes(d.need)} (tiles + merged), {formatBytes(d.free)}{' '}
                        free
                        {d.low && ' — not enough space'}
                      </p>
                    ))}
                    <p className="text-[10px] text-slate-500">
                      Upper bound for {storage.active_lakes} lakes; lake-years already in the
                      current format are skipped. Tiles can be deleted in the merge step.
                    </p>
                  </div>
                )}
                {lowSpace && (
                  <p className="text-[10px] text-amber-400">
                    A drive may run out of space — choose another folder for some years.
                  </p>
                )}
                <p className="text-[10px] text-slate-500">
                  Years go to {storage.default_root}/&lt;year&gt; unless you pick another folder.
                  Existing images are found through the paths in lake_images / lake_tiles and stay
                  where they are; merge writes next to the tiles.
                </p>
              </div>
            )}
          </div>

          {/* Info box */}
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <p className="text-xs leading-relaxed text-slate-400">
              Downloads one Sentinel-2 Surface Reflectance (L2A, harmonized) yearly median composite
              per lake at 30 m, on a fixed global grid. Clouds and shadows are masked with Cloud
              Score+ (cs_cdf ≥ 0.6) plus SCL saturated / snow pixels. Each lake polygon is buffered
              by 3.5 km and split into 25 km tiles that are downloaded from Google Earth Engine.
            </p>
            <div className="mt-2.5 grid grid-cols-1 gap-x-3 gap-y-1 sm:grid-cols-2">
              {BANDS.map((b) => (
                <div key={b.id} className="flex items-baseline gap-1.5 text-[11px]">
                  <span
                    className={clsx(
                      'w-[4.5rem] shrink-0 font-mono',
                      b.prithvi ? 'text-cyan-300' : 'text-slate-300',
                    )}
                  >
                    {b.id}
                  </span>
                  <span className="text-slate-500">{b.name}</span>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] text-slate-500">
              <span className="text-cyan-300">Cyan</span> bands feed the Prithvi embedding; all 11
              spectral bands are used for lake features. 12 bands, uint16 (reflectance × 10000,
              nodata 65535).
            </p>
            <p className="mt-1.5 text-[10px] text-slate-500">
              Lake-years that are already downloaded (or merged) in the current format are skipped.
            </p>
          </div>

          {/* Progress */}
          {progress && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="flex min-w-0 items-center gap-1.5 text-slate-400">
                  {isActive && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-cyan-400" />}
                  <span className="truncate">{statusLabel}</span>
                </span>
                <span className="shrink-0 font-mono text-slate-300">
                  {progress.processed} / {progress.total} lake-years · {progressPercent}%
                </span>
              </div>

              <div
                className="h-2 overflow-hidden rounded-full bg-slate-700/60"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progressPercent}
              >
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500 ease-out',
                    isDone && progress.failed === 0
                      ? 'bg-emerald-500'
                      : isDone
                        ? 'bg-amber-500'
                        : isFailed || isCancelled || isCancelling
                          ? 'bg-red-500'
                          : 'bg-cyan-500',
                  )}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {progress.success} downloaded
                </span>
                <span className="flex items-center gap-1 text-slate-400">
                  <CheckCircle2 className="h-3 w-3" />
                  {progress.skipped} already done
                </span>
                <span className="flex items-center gap-1 text-red-400">
                  <XCircle className="h-3 w-3" />
                  {progress.failed} failed
                </span>
                <span className="text-slate-500">
                  tiles: {progress.tiles_completed} ok
                  {progress.tiles_failed > 0 && `, ${progress.tiles_failed} failed`}
                  {isActive &&
                    progress.active_lakes > 0 &&
                    ` · ${progress.active_lakes} lakes in progress`}
                </span>
              </div>

              {Object.keys(progress.year_roots ?? {}).length > 0 && (
                <div className="space-y-0.5">
                  {Object.entries(progress.year_roots).map(([year, root]) => (
                    <p
                      key={year}
                      className="truncate font-mono text-[10px] text-slate-500"
                      title={root}
                    >
                      {year} → {root}
                    </p>
                  ))}
                </div>
              )}

              {progress.errors.length > 0 && (
                <div className="max-h-24 overflow-y-auto rounded-lg border border-red-500/30 bg-red-500/5 p-2 scrollbar-thin">
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
                  You can close this dialog — the download keeps running and progress is shown again
                  when you reopen it.
                </p>
              )}
            </div>
          )}

          {/* Status messages */}
          {result && !progress && (
            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3 text-xs text-cyan-300">
              {result.message}
            </div>
          )}
          {pollWarning && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-400">
              {pollWarning}
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
              {error}
            </div>
          )}
        </div>

        {/* Destination summary — what the Fetch button will actually send */}
        {!isActive && selectedYears.length > 0 && storage && (
          <div className="border-t border-slate-700/60 px-5 py-2.5">
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Will save to</p>
            {[...selectedYears].reverse().map((year) => (
              <p key={year} className="truncate font-mono text-[11px] text-slate-300" title={`${targetFor(year)}/${year}`}>
                {year} → {targetFor(year)}/{year}/
              </p>
            ))}
          </div>
        )}

        {/* ── Footer ──────────────────────────────────────────────── */}
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
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg border px-4 py-2 text-xs font-medium transition-colors',
                isCancelling
                  ? 'cursor-not-allowed border-slate-700 text-slate-500'
                  : 'border-red-500/40 bg-red-500/15 text-red-400 hover:bg-red-500/25 hover:text-red-300',
              )}
            >
              {isCancelling ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <XCircle className="h-3.5 w-3.5" />
              )}
              {isCancelling ? 'Cancelling…' : 'Cancel Download'}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleFetch}
              disabled={!canStart}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
                !canStart
                  ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                  : 'bg-cyan-600 text-white hover:bg-cyan-500',
              )}
            >
              {starting ? (
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
