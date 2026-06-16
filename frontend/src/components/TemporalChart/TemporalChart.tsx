import { useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import Card from '@/components/common/Card';
import { useTemporal } from '@/hooks/useTemporal';
import { useMapStore } from '@/store/mapStore';

const INDICATORS = [
  { key: 'ndvi', label: 'NDVI', color: '#22c55e', desc: 'Vegetation' },
  { key: 'ndwi', label: 'NDWI', color: '#3b82f6', desc: 'Water' },
  { key: 'nbr', label: 'NBR', color: '#f97316', desc: 'Burn Severity' },
] as const;

type IndicatorKey = 'ndvi' | 'ndwi' | 'nbr';

interface ChartRow {
  year: number;
  ndvi?: number;
  ndwi?: number;
  nbr?: number;
}

// Custom tooltip
function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-surface-800 border border-slate-700/60 px-3 py-2 shadow-xl">
      <p className="mb-1.5 text-xs font-semibold text-slate-300">Year {label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center justify-between gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            {entry.name}
          </span>
          <span className="font-mono font-medium text-slate-200">
            {entry.value.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function TemporalChart() {
  const { selectedRegionId } = useMapStore();
  const { data, isLoading, error, refetch } = useTemporal(selectedRegionId);
  const [visible, setVisible] = useState<Set<IndicatorKey>>(
    new Set(['ndvi', 'ndwi', 'nbr']),
  );

  const chartData = useMemo<ChartRow[]>(() => {
    if (!data) return [];

    const yearSet = new Set<number>([
      ...data.ndvi.map((d) => d.year),
      ...data.ndwi.map((d) => d.year),
      ...data.nbr.map((d) => d.year),
    ]);

    const ndviMap = new Map(data.ndvi.map((d) => [d.year, d.value]));
    const ndwiMap = new Map(data.ndwi.map((d) => [d.year, d.value]));
    const nbrMap = new Map(data.nbr.map((d) => [d.year, d.value]));

    return Array.from(yearSet)
      .sort()
      .map((year) => ({
        year,
        ndvi: ndviMap.get(year),
        ndwi: ndwiMap.get(year),
        nbr: nbrMap.get(year),
      }));
  }, [data]);

  const toggleIndicator = (key: IndicatorKey) => {
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key); // always keep at least one
      } else {
        next.add(key);
      }
      return next;
    });
  };

  if (!selectedRegionId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-slate-400">Select a region to view temporal trends</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" label="Loading temporal data…" />
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

  if (!data || chartData.length === 0) {
    return (
      <div className="p-4">
        <Card>
          <p className="text-center text-sm text-slate-500">
            No temporal data available for this region.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-3 tab-content-enter">
      {/* Indicator toggles */}
      <div className="flex flex-wrap gap-2">
        {INDICATORS.map(({ key, label, color, desc }) => (
          <button
            key={key}
            onClick={() => toggleIndicator(key)}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs
                        font-medium transition-all ${
                          visible.has(key)
                            ? 'border-transparent text-white'
                            : 'border-slate-700 bg-transparent text-slate-500'
                        }`}
            style={
              visible.has(key)
                ? { backgroundColor: color + '33', borderColor: color + '66', color }
                : {}
            }
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: visible.has(key) ? color : '#475569' }}
            />
            {label} — {desc}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="rounded-xl bg-surface-800 border border-slate-700/60 p-4">
        <p className="mb-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Annual Environmental Indices ({chartData[0]?.year}–{chartData[chartData.length - 1]?.year})
        </p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart
            data={chartData}
            margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="year"
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={false}
            />
            <YAxis
              domain={[-1, 1]}
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            {INDICATORS.filter((i) => visible.has(i.key)).map(
              ({ key, label, color }) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={label}
                  stroke={color}
                  strokeWidth={2}
                  dot={{ r: 3, fill: color }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              ),
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-2">
        {INDICATORS.filter((i) => visible.has(i.key)).map(({ key, label, color }) => {
          const vals = chartData
            .map((d) => d[key as keyof ChartRow] as number | undefined)
            .filter((v): v is number => v !== undefined);
          const mean = vals.reduce((a, b) => a + b, 0) / (vals.length || 1);
          const last = vals[vals.length - 1];
          const first = vals[0];
          const delta = last !== undefined && first !== undefined ? last - first : 0;

          return (
            <div
              key={key}
              className="rounded-lg bg-surface-900/60 border border-slate-700/40 p-2.5 text-center"
            >
              <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color }}>
                {label}
              </p>
              <p className="font-mono text-sm font-bold text-slate-200">
                {mean.toFixed(3)}
              </p>
              <p className="text-[10px] text-slate-500">mean</p>
              <p
                className={`text-[10px] font-medium ${
                  delta > 0 ? 'text-emerald-400' : delta < 0 ? 'text-red-400' : 'text-slate-500'
                }`}
              >
                {delta >= 0 ? '+' : ''}{delta.toFixed(3)} Δ
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
