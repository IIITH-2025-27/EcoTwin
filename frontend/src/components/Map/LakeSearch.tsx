import { useEffect, useRef, useState } from 'react';
import { Loader2, Search, X } from 'lucide-react';

import { searchLakes } from '@/api/regions';
import type { LakeSearchResult } from '@/types';

interface LakeSearchProps {
  onSelect: (lake: LakeSearchResult) => void;
}

export default function LakeSearch({ onSelect }: LakeSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<LakeSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 3) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }

    const currentRequest = ++requestId.current;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const lakes = await searchLakes(term);
        if (requestId.current === currentRequest) setResults(lakes);
      } catch {
        if (requestId.current === currentRequest) {
          setResults([]);
          setError('Could not search lakes.');
        }
      } finally {
        if (requestId.current === currentRequest) setLoading(false);
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [query]);

  const selectLake = (lake: LakeSearchResult) => {
    setQuery(lake.display_name);
    setResults([]);
    onSelect(lake);
  };

  return (
    <div className="absolute left-1/2 top-3 z-[1000] w-[min(28rem,calc(100%-2rem))] -translate-x-1/2">
      <div className="rounded-lg border border-slate-600/70 bg-surface-800/95 shadow-xl backdrop-blur-sm">
        <div className="flex items-center gap-2 px-3 py-2">
          <Search className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search lakes by name…"
            aria-label="Search lakes by display name"
            className="min-w-0 flex-1 bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
          />
          {loading && <Loader2 className="h-4 w-4 animate-spin text-primary-400" />}
          {query && !loading && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="rounded p-0.5 text-slate-400 hover:bg-slate-700 hover:text-slate-100"
              aria-label="Clear lake search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {query.trim().length > 0 && query.trim().length < 3 && (
          <p className="border-t border-slate-700/70 px-3 py-2 text-xs text-slate-400">
            Type at least 3 characters to search.
          </p>
        )}
        {(results.length > 0 || error) && (
          <div className="max-h-72 overflow-y-auto border-t border-slate-700/70 py-1">
            {error ? (
              <p className="px-3 py-2 text-xs text-rose-300">{error}</p>
            ) : (
              results.map((lake) => (
                <button
                  key={lake.lake_id}
                  type="button"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    selectLake(lake);
                  }}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-slate-700/60"
                >
                  <span className="min-w-0 truncate text-sm text-slate-100">{lake.display_name}</span>
                  <span className="shrink-0 text-xs text-slate-400">{lake.state ?? 'India'}</span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
