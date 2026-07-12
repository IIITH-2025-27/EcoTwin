import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Database, Loader2, RefreshCw, X } from 'lucide-react';
import { clsx } from 'clsx';

import { fetchSyncCountry, importLakesTable, type LakeImportResponse } from '@/api/sync';

interface SyncLakesModalProps {
  onClose: () => void;
}

export default function SyncLakesModal({ onClose }: SyncLakesModalProps) {
  const [country, setCountry] = useState('India');
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState<LakeImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSyncCountry().then((config) => setCountry(config.country)).catch(() => undefined);
  }, []);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    setResult(null);
    try {
      setResult(await importLakesTable(country));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to sync lakes.');
    } finally {
      setSyncing(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-lakes-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary-600/30 bg-primary-600/20">
              <Database className="h-4 w-4 text-primary-400" />
            </div>
            <div>
              <h2 id="sync-lakes-title" className="text-sm font-semibold text-slate-100">Sync Lakes</h2>
              <p className="text-xs text-slate-500">Import HydroLAKES records into the lakes table</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-700/50 hover:text-slate-200" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div className="rounded-lg border border-slate-700/60 bg-surface-800 p-3">
            <p className="text-xs font-medium text-slate-300">Region source</p>
            <p className="mt-1 text-sm text-slate-100">{country}</p>
          </div>
          <p className="text-xs leading-relaxed text-slate-400">
            This imports lake metadata and geometries from the shared HydroLAKES shapefile. It does not run the ML data pipeline.
          </p>
          {result && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
              {result.message} Added {result.inserted_records}, updated {result.updated_records}, skipped {result.skipped_records}.
            </div>
          )}
          {error && <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">{error}</div>}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-700/60 px-5 py-3">
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-xs text-slate-400 transition-colors hover:bg-slate-700/50 hover:text-slate-200">
            Close
          </button>
          <button
            type="button"
            onClick={handleSync}
            disabled={syncing}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              syncing ? 'cursor-wait bg-slate-700 text-slate-400' : 'bg-primary-600 text-white hover:bg-primary-500',
            )}
          >
            {syncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {syncing ? 'Syncing lakes…' : 'Sync Lakes'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
