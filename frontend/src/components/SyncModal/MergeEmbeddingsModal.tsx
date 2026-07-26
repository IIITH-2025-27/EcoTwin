import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Layers, Loader2, X, CheckCircle2, Globe2 } from 'lucide-react';
import { clsx } from 'clsx';

import { getAvailableEmbeddingYears, mergeEmbeddings, type MergeEmbeddingsResponse } from '@/api/embeddings';

interface MergeEmbeddingsModalProps {
  onClose: () => void;
}

const SUPPORTED_COUNTRIES = ['India'];

export default function MergeEmbeddingsModal({ onClose }: MergeEmbeddingsModalProps) {
  const [selectedCountry, setSelectedCountry] = useState('India');
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingYears, setLoadingYears] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MergeEmbeddingsResponse | null>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    let ignore = false;

    const fetchAvailableYears = async () => {
      setLoadingYears(true);
      setError(null);
      setResult(null);

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

    void fetchAvailableYears();

    return () => {
      ignore = true;
    };
  }, []);

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

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await mergeEmbeddings({
        years: filteredYears,
        country: selectedCountry,
        confirmed: true,
      });
      setResult(response);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start embedding merge.');
    } finally {
      setLoading(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-embeddings-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-slate-700/60 bg-surface-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/15">
              <Layers className="h-4 w-4 text-emerald-400" />
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
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200" aria-label="Close">
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
                className="w-full bg-transparent text-sm text-slate-200 outline-none"
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
                      onClick={() => toggleYear(year)}
                      className={clsx(
                        'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                        isSelected
                          ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300'
                          : 'border-slate-700/60 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-300',
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

          {result && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4" />
                <span>{result.message}</span>
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-700/60 px-5 py-3">
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-xs text-slate-400 transition-colors hover:bg-slate-700/50 hover:text-slate-200">
            Close
          </button>
          <button
            type="button"
            onClick={handleMerge}
            disabled={loading || loadingYears || availableYears.length === 0 || selectedYears.filter((year) => availableYears.includes(year)).length === 0}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium transition-colors',
              loading || loadingYears || availableYears.length === 0 || selectedYears.filter((year) => availableYears.includes(year)).length === 0
                ? 'cursor-not-allowed bg-slate-700 text-slate-500'
                : 'bg-emerald-600 text-white hover:bg-emerald-500',
            )}
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
            Merge Embeddings
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
