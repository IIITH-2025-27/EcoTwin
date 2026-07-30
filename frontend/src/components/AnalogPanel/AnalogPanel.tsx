import React from 'react';
import { MapPin, Timer, ArrowRight, Zap, Ruler, GitMerge } from 'lucide-react';
import { clsx } from 'clsx';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import Card from '@/components/common/Card';
import { useSimilarity } from '@/hooks/useSimilarity';
import { useMapStore } from '@/store/mapStore';
import type { AnalogResult, SimilarityMethod } from '@/types';

// ── Similarity ring ───────────────────────────────────────────────────────
function SimilarityRing({ score }: { score: number }) {
  const pct = score * 100;
  const r = 18;
  const circ = 2 * Math.PI * r;
  const dashOffset = circ - (pct / 100) * circ;
  const color =
    score >= 0.85
      ? '#22c55e'
      : score >= 0.70
      ? '#84cc16'
      : score >= 0.55
      ? '#eab308'
      : score >= 0.40
      ? '#f97316'
      : '#ef4444';

  return (
    <div className="relative flex-shrink-0">
      <svg width="44" height="44" className="-rotate-90">
        <circle
          cx="22" cy="22" r={r}
          fill="none"
          stroke="#1e293b"
          strokeWidth="3"
        />
        <circle
          cx="22" cy="22" r={r}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeDasharray={circ}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center font-mono text-[10px] font-bold"
        style={{ color }}
      >
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}

// ── Analog card ───────────────────────────────────────────────────────────
function AnalogCard({
  analog,
  rank,
  isHighlighted,
  onHover,
  onClick,
}: {
  analog: AnalogResult;
  rank: number;
  isHighlighted: boolean;
  onHover: (id: string | null) => void;
  onClick: (analog: AnalogResult) => void;
}) {
  return (
    <button
      className={clsx(
        'w-full rounded-xl border p-3 text-left transition-all duration-150',
        'flex items-center gap-3',
        isHighlighted
          ? 'border-primary-500/50 bg-primary-900/20 ring-1 ring-primary-500/30'
          : 'border-slate-700/50 bg-surface-800 hover:border-slate-600/60 hover:bg-surface-700/60',
      )}
      onMouseEnter={() => onHover(analog.region_id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onClick(analog)}
    >
      {/* Rank */}
      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-slate-700/60 text-xs font-bold text-slate-300">
        {rank}
      </span>

      {/* Similarity ring */}
      <SimilarityRing score={analog.similarity_score} />

      {/* Details */}
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[11px] text-slate-400 truncate">
          {analog.region_id.slice(0, 20)}…
        </p>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
          <span className="flex items-center gap-0.5">
            <MapPin className="h-2.5 w-2.5" />
            {analog.center_lat.toFixed(3)}, {analog.center_lon.toFixed(3)}
          </span>
          <span>Year {analog.year}</span>
          {analog.dominant_ecosystem && (
            <span className="capitalize text-slate-400">
              {analog.dominant_ecosystem}
            </span>
          )}
        </div>
      </div>

      <ArrowRight className="h-3.5 w-3.5 flex-shrink-0 text-slate-600" />
    </button>
  );
}

// ── Method selector config ────────────────────────────────────────────────
const METHODS: Array<{
  value: SimilarityMethod;
  label: string;
  icon: React.ReactNode;
  tip: string;
}> = [
  {
    value: 'cosine',
    label: 'Cosine',
    icon: <Zap className="h-3 w-3" />,
    tip: 'Cosine similarity — angle between embeddings. Best for unit-norm Prithvi vectors.',
  },
  {
    value: 'euclidean',
    label: 'Euclidean',
    icon: <Ruler className="h-3 w-3" />,
    tip: 'Euclidean (L2) distance — magnitude-aware. Score = 1 / (1 + distance).',
  },
  {
    value: 'knn',
    label: 'KNN',
    icon: <GitMerge className="h-3 w-3" />,
    tip: 'Exact k-NN inner product — equivalent to cosine on normalised embeddings.',
  },
];

// ── Main component ────────────────────────────────────────────────────────
export default function AnalogPanel() {
  const {
    selectedRegionId,
    topK,
    setTopK,
    similarityMethod,
    setSimilarityMethod,
    highlightedAnalogId,
    setHighlightedAnalogId,
    selectRegion,
    setActiveTab,
  } = useMapStore();

  const { data, isLoading, error, refetch } = useSimilarity(
    selectedRegionId,
    topK,
    undefined,
    similarityMethod,
  );

  if (!selectedRegionId) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center px-4">
        <p className="text-sm text-slate-400">Select a region to see analogs</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" label="Searching for analogs…" />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorMessage
        message={error.message}
        onRetry={() => refetch()}
        className="m-4"
      />
    );
  }

  if (!data) return null;

  if (data.analogs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center px-4">
        <p className="text-sm text-slate-400">No similarity embeddings are available for this lake yet.</p>
        <p className="text-xs text-slate-500">
          Try another lake that has historical embeddings, or switch to a different sub-region.
        </p>
      </div>
    );
  }

  const handleAnalogClick = (analog: AnalogResult) => {
    selectRegion(analog.region_id, analog.center_lat, analog.center_lon);
    setActiveTab('overview');
  };

  return (
    <div className="space-y-3 p-3 tab-content-enter">
      {/* Method selector */}
      <div className="flex gap-1 rounded-lg bg-surface-800/60 border border-slate-700/40 p-1">
        {METHODS.map(({ value, label, icon, tip }) => (
          <button
            key={value}
            title={tip}
            onClick={() => setSimilarityMethod(value)}
            className={clsx(
              'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors',
              similarityMethod === value
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/40',
            )}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Timer className="h-3.5 w-3.5 text-slate-500" />
          {data.search_latency_ms.toFixed(0)} ms · Year {data.query_year}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-500">Top-K</label>
          <select
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            className="rounded bg-surface-800 border border-slate-700 px-2 py-0.5
                       text-xs text-slate-300 focus:outline-none focus:ring-1
                       focus:ring-primary-500/50"
          >
            {[5, 10, 15, 20].map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Results count */}
      <p className="text-xs text-slate-500">
        {data.analogs.length} ecosystem analog
        {data.analogs.length !== 1 ? 's' : ''} found
      </p>

      {/* Analog cards */}
      <div className="space-y-2">
        {data.analogs.map((analog, i) => (
          <AnalogCard
            key={analog.region_id}
            analog={analog}
            rank={i + 1}
            isHighlighted={analog.region_id === highlightedAnalogId}
            onHover={setHighlightedAnalogId}
            onClick={handleAnalogClick}
          />
        ))}
      </div>

      {data.analogs.length === 0 && (
        <Card>
          <p className="text-center text-sm text-slate-500">
            No analog ecosystems found. Try increasing the Top-K value.
          </p>
        </Card>
      )}
    </div>
  );
}
