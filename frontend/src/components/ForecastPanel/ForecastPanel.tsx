import { useMemo, useState } from 'react';
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus, Info, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import Card from '@/components/common/Card';
import Badge, { trendToBadgeVariant } from '@/components/common/Badge';
import { useForecast } from '@/hooks/useForecast';
import { useEcologicalForecast } from '@/hooks/useEcologicalForecast';
import { useMapStore } from '@/store/mapStore';
import type { TrendDirection, EcologicalForecastData, EcoDirection } from '@/types';

type IndicatorKey = 'ndvi' | 'ndwi' | 'nbr';

const ECO_CHART_INDICES = [
  { key: 'ndci', label: 'NDCI', color: '#06b6d4' },
  { key: 'ndvi_b7', label: 'NDVI-B7', color: '#22c55e' },
  { key: 'turbidity_ratio', label: 'Turbidity', color: '#f59e0b' },
  { key: 'red_edge_slope', label: 'RE Slope', color: '#a855f7' },
] as const;

type EcoChartKey = (typeof ECO_CHART_INDICES)[number]['key'];

const INDICATORS: Array<{
  key: IndicatorKey;
  label: string;
  forecastKey: 'ndvi_forecast' | 'ndwi_forecast' | 'nbr_forecast';
  color: string;
  trendKey: 'vegetation_trend' | 'water_trend' | 'burn_severity_trend';
  trendLabel: string;
}> = [
  {
    key: 'ndvi',
    label: 'NDVI',
    forecastKey: 'ndvi_forecast',
    color: '#22c55e',
    trendKey: 'vegetation_trend',
    trendLabel: 'Vegetation',
  },
  {
    key: 'ndwi',
    label: 'NDWI',
    forecastKey: 'ndwi_forecast',
    color: '#3b82f6',
    trendKey: 'water_trend',
    trendLabel: 'Water',
  },
  {
    key: 'nbr',
    label: 'NBR',
    forecastKey: 'nbr_forecast',
    color: '#f97316',
    trendKey: 'burn_severity_trend',
    trendLabel: 'Burn',
  },
];

function TrendIcon({ direction }: { direction: TrendDirection }) {
  if (direction === 'increasing')
    return <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />;
  if (direction === 'declining')
    return <TrendingDown className="h-3.5 w-3.5 text-red-400" />;
  return <Minus className="h-3.5 w-3.5 text-slate-400" />;
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444';
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">Overall Confidence</span>
        <span className="font-mono font-bold" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-700/60">
        <div
          className="h-2 rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

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
      {payload.map((entry) =>
        entry.value !== null && entry.value !== undefined ? (
          <div
            key={entry.name}
            className="flex items-center justify-between gap-4 text-xs"
          >
            <span className="flex items-center gap-1.5 text-slate-400">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              {entry.name}
            </span>
            <span className="font-mono font-medium text-slate-200">
              {typeof entry.value === 'number' ? entry.value.toFixed(4) : entry.value}
            </span>
          </div>
        ) : null,
      )}
    </div>
  );
}

export default function ForecastPanel() {
  const { selectedRegionId, similarityMethod } = useMapStore();
  const [selectedEcoSeries, setSelectedEcoSeries] = useState<EcoChartKey | 'all'>('all');

  const { data: forecast, isLoading: fLoading, error: fError, refetch: fRefetch } =
    useForecast(selectedRegionId, similarityMethod);
  const { data: ecoForecast, isLoading: ecoLoading } =
    useEcologicalForecast(selectedRegionId, similarityMethod);

  const ecoChartData = useMemo(() => {
    if (!ecoForecast) return [];

    const years = [ecoForecast.current_year, ...(ecoForecast.forecast_years ?? [])];
    const indexForecastMap = new Map(ecoForecast.index_forecasts?.map((item) => [item.index_name, item]) ?? []);

    return years.map((year, index) => {
      const row: Record<string, number | string | null> = { year };

      ECO_CHART_INDICES.forEach(({ key }) => {
        const forecastEntry = indexForecastMap.get(key);
        const baseValue = forecastEntry?.current_value ?? 0;

        if (index === 0) {
          row[key] = baseValue;
          return;
        }

        const targetYear = year;
        const values = (ecoForecast.twins_used ?? [])
          .map((twin) => {
            const yearMap = twin.index_values?.[key];
            const rawValue = yearMap ? yearMap[String(targetYear)] ?? yearMap[targetYear as unknown as string] : undefined;
            return rawValue == null ? null : { value: Number(rawValue), weight: twin.fixed_weight };
          })
          .filter((item): item is { value: number; weight: number } => item !== null);

        if (values.length) {
          const totalWeight = values.reduce((sum, item) => sum + item.weight, 0);
          const weightedValue = values.reduce((sum, item) => sum + item.value * item.weight, 0) / totalWeight;
          row[key] = weightedValue;
          return;
        }

        const yearlyDirections = forecastEntry?.yearly_directions ?? [];
        const priorValue = index === 1 ? baseValue : row[key] ?? baseValue;
        const numericPriorValue = typeof priorValue === 'number' ? priorValue : Number(priorValue ?? 0);
        const yearOffset = index - 1;
        const cumulativeDelta = yearlyDirections
          .slice(0, yearOffset)
          .reduce((sum, item) => sum + (item.weighted_score ?? 0), 0);
        row[key] = numericPriorValue + cumulativeDelta;
      });

      return row;
    });
  }, [ecoForecast]);

  const splitYear = forecast?.current_year;
  const visibleEcoSeries = selectedEcoSeries === 'all'
    ? ECO_CHART_INDICES
    : ECO_CHART_INDICES.filter((item) => item.key === selectedEcoSeries);

  if (!selectedRegionId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-slate-400">Select a region to see forecasts</p>
      </div>
    );
  }

  if (fLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" label="Generating forecast…" />
      </div>
    );
  }

  if (fError) {
    return (
      <ErrorMessage
        message={fError.message}
        onRetry={() => fRefetch()}
        className="m-4"
      />
    );
  }

  if (!forecast && !ecoForecast) return null;

  return (
    <div className="space-y-3 p-3 tab-content-enter">
      {forecast && (
        <>
          {/* Analog match info */}
          {forecast.best_analog_id && (
            <Card>
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-slate-300">Best Analog Match</p>
                <p className="font-mono text-[11px] text-slate-400 break-all">
                  {forecast.best_analog_id.slice(0, 24)}…
                </p>
                {forecast.analog_match_year && (
                  <p className="text-xs text-slate-500">
                    Matched at historical year{' '}
                    <span className="text-primary-400 font-medium">
                      {forecast.analog_match_year}
                    </span>
                  </p>
                )}
                <ConfidenceBar value={forecast.overall_confidence} />
              </div>
            </Card>
          )}

          {/* Trend badges */}
          <div className="grid grid-cols-3 gap-2">
            {INDICATORS.map((i) => {
              const trend = forecast[i.trendKey];
              return (
                <div
                  key={i.key}
                  className="rounded-lg bg-surface-800 border border-slate-700/40 p-2 text-center"
                >
                  <p className="text-[10px] text-slate-500 mb-1">{i.trendLabel}</p>
                  <div className="flex items-center justify-center gap-1">
                    <TrendIcon direction={trend} />
                    <Badge
                      label={trend}
                      variant={trendToBadgeVariant(trend)}
                      className="capitalize"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Ecological index chart */}
      <div className="rounded-xl bg-surface-800 border border-slate-700/60 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setSelectedEcoSeries('all')}
            className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition ${selectedEcoSeries === 'all' ? 'bg-cyan-500/20 text-cyan-300' : 'bg-surface-900/70 text-slate-400 hover:text-slate-200'}`}
          >
            All
          </button>
          {ECO_CHART_INDICES.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setSelectedEcoSeries(key)}
              className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition ${selectedEcoSeries === key ? 'bg-cyan-500/20 text-cyan-300' : 'bg-surface-900/70 text-slate-400 hover:text-slate-200'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mb-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {selectedEcoSeries === 'all' ? 'Expected ecological index values for target lake' : `Expected ${ECO_CHART_INDICES.find((item) => item.key === selectedEcoSeries)?.label} values`}
        </p>
        {ecoChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={ecoChartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="year"
                tick={{ fill: '#64748b', fontSize: 10 }}
                axisLine={{ stroke: '#334155' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 10 }}
                axisLine={{ stroke: '#334155' }}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              {visibleEcoSeries.map(({ key, label, color }) => (
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
              ))}
              {splitYear && (
                <ReferenceLine
                  x={splitYear}
                  stroke="#64748b"
                  strokeDasharray="4 3"
                  label={{
                    value: 'Now',
                    position: 'insideTopRight',
                    fill: '#64748b',
                    fontSize: 10,
                  }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[220px] items-center justify-center text-xs text-slate-400">
            No ecological twin forecast values available yet.
          </div>
        )}
      </div>

      <EcologicalForecastSection data={ecoForecast} isLoading={ecoLoading} />
    </div>
  );
}

/* ── Ecological index forecast sub-component ─────────────────────────── */

const ECO_INDICES = [
  { key: 'ndci', label: 'NDCI', desc: 'Chlorophyll-a', color: '#06b6d4' },
  { key: 'ndvi_b7', label: 'NDVI-B7', desc: 'Vegetation Vigor', color: '#22c55e' },
  { key: 'turbidity_ratio', label: 'Turbidity', desc: 'Water Clarity', color: '#f59e0b' },
  { key: 'red_edge_slope', label: 'RE Slope', desc: 'Pigment Trend', color: '#a855f7' },
] as const;

const DIR_ARROW: Record<string, string> = { up: '↑', down: '↓', stable: '→', uncertain: '?' };
const DIR_LABEL: Record<string, string> = {
  up: 'Upward',
  down: 'Downward',
  stable: 'Stable',
  uncertain: 'Uncertain',
};
const DIR_CLR: Record<string, string> = {
  up: 'text-emerald-400', down: 'text-red-400', stable: 'text-slate-400', uncertain: 'text-amber-400',
};

type EcoIndexKey = (typeof ECO_INDICES)[number]['key'];
type EcoTrendDirection = 'up' | 'down' | 'stable' | 'uncertain';

function EcoTrendIcon({ direction }: { direction: EcoTrendDirection }) {
  const base = 'text-lg font-semibold';

  if (direction === 'up') {
    return <span className={`${base} text-emerald-400`}>↑</span>;
  }

  if (direction === 'down') {
    return <span className={`${base} text-red-400`}>↓</span>;
  }

  if (direction === 'stable') {
    return <span className={`${base} text-slate-400`}>→</span>;
  }

  return <span className={`${base} text-amber-400`}>?</span>;
}

function EcologicalForecastSection({ data, isLoading }: { data: EcologicalForecastData | undefined; isLoading: boolean }) {
  const [selectedIndex, setSelectedIndex] = useState<EcoIndexKey>('ndci');
  const [twinsExpanded, setTwinsExpanded] = useState(false);
  const [reportExpanded, setReportExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="mt-2">
        <LoadingSpinner size="sm" label="Loading ecological forecast…" />
      </div>
    );
  }

  if (!data || !data.forecast_years?.length) return null;

  const fcMap = new Map(data.index_forecasts.map((f) => [f.index_name, f]));
  const activeMeta = ECO_INDICES.find((i) => i.key === selectedIndex) ?? ECO_INDICES[0];
  const activeForecast = fcMap.get(activeMeta.key);
  const totalTwins = activeForecast?.yearly_directions.reduce(
    (sum, item) => sum + item.twins_contributing,
    0,
  );

  return (
    <div className="space-y-3 mt-1">
      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-slate-700/60" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Ecological Index Forecast
        </span>
        <div className="h-px flex-1 bg-slate-700/60" />
      </div>

      <div className="rounded-xl bg-surface-800 border border-slate-700/60 p-3">
        <div className="flex gap-1">
          {ECO_INDICES.map(({ key, label, color }) => (
            <button
              key={key}
              onClick={() => setSelectedIndex(key)}
              className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-all ${
                selectedIndex === key
                  ? 'text-white'
                  : 'bg-surface-900/60 text-slate-500 hover:text-slate-300'
              }`}
              style={
                selectedIndex === key
                  ? { backgroundColor: `${color}33`, color, borderBottom: `2px solid ${color}` }
                  : {}
              }
            >
              {label}
            </button>
          ))}
        </div>

        {activeForecast && (
          <div className="mt-3 rounded-lg bg-surface-900/60 border border-slate-700/30 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wide" style={{ color: activeMeta.color }}>
                  {activeMeta.label}
                </p>
                <p className="mt-1 text-[11px] text-slate-500">{activeMeta.desc}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Current</p>
                <p className="font-mono text-lg font-semibold text-slate-100">
                  {activeForecast.current_value.toFixed(4)}
                </p>
              </div>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {activeForecast.yearly_directions.map((yd) => {
                const direction = yd.direction as EcoTrendDirection;
                return (
                  <div key={yd.year} className="rounded-md border border-slate-700/40 bg-surface-800/70 p-2.5 text-center">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">Year {yd.year}</p>
                    <div className="mt-1 flex items-center justify-center gap-1">
                      <EcoTrendIcon direction={direction} />
                      <span className={`text-xs font-semibold ${DIR_CLR[yd.direction] ?? 'text-slate-400'}`}>
                        {DIR_LABEL[yd.direction] ?? 'Unknown'}
                      </span>
                    </div>
                    <p className="mt-1 text-[9px] text-slate-500">
                      {yd.twins_contributing} twins • {yd.weighted_score.toFixed(2)}
                    </p>
                  </div>
                );
              })}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-700/40 bg-surface-800/50 px-2.5 py-2 text-[10px] text-slate-500">
              <span>Forecast window: {data.forecast_years.join(', ')}</span>
              <span>Contributing twins: {totalTwins ?? 0}</span>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-xl bg-surface-800 border border-slate-700/60 overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700/60">
              <th className="py-2 px-3 text-left text-slate-500 font-medium">Index</th>
              <th className="py-2 px-3 text-center text-slate-500 font-medium font-mono">{data.current_year}<br /><span className="text-[9px] text-slate-600">current</span></th>
              {data.forecast_years.map((yr) => (
                <th key={yr} className="py-2 px-3 text-center text-slate-500 font-medium font-mono">{yr}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ECO_INDICES.map(({ key, label, color }, ri) => {
              const fc = fcMap.get(key);
              if (!fc) return null;
              return (
                <tr key={key} className={`border-b border-slate-700/30 ${ri % 2 ? 'bg-slate-800/30' : ''}`}>
                  <td className="py-2.5 px-3">
                    <span className="font-semibold text-[11px]" style={{ color }}>
                      {label}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-center font-mono text-slate-300 text-[11px]">
                    {fc.current_value.toFixed(4)}
                  </td>
                  {fc.yearly_directions.map((yd) => (
                    <td key={yd.year} className="py-2.5 px-3 text-center">
                      <span
                        className={`text-lg font-bold ${DIR_CLR[yd.direction] ?? 'text-slate-400'}`}
                        title={`score: ${yd.weighted_score.toFixed(4)}, ${yd.twins_contributing} twins`}
                      >
                        {DIR_ARROW[yd.direction] ?? '?'}
                      </span>
                      <p className="text-[9px] text-slate-600 mt-0.5">{yd.twins_contributing}tw</p>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-center gap-4 text-[10px] text-slate-500">
        <span><span className="text-emerald-400 font-bold">↑</span> Upward</span>
        <span><span className="text-red-400 font-bold">↓</span> Downward</span>
        <span><span className="text-slate-400 font-bold">→</span> Stable</span>
        <span><span className="text-amber-400 font-bold">?</span> Uncertain</span>
      </div>

      {data.twins_used.length > 0 && (
        <div className="rounded-xl bg-surface-800 border border-slate-700/60 overflow-hidden">
          <button
            onClick={() => setTwinsExpanded((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span className="font-medium">Twin Lakes ({data.twins_used.length})</span>
            {twinsExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {twinsExpanded && (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-t border-b border-slate-700/60">
                  <th className="py-1.5 px-2 text-left text-slate-500 font-medium">Rank</th>
                  <th className="py-1.5 px-2 text-left text-slate-500 font-medium">Lake</th>
                  <th className="py-1.5 px-2 text-right text-slate-500 font-medium">Match Yr</th>
                  <th className="py-1.5 px-2 text-right text-slate-500 font-medium">Similarity</th>
                  <th className="py-1.5 px-2 text-right text-slate-500 font-medium">Weight</th>
                  <th className="py-1.5 px-2 text-right text-slate-500 font-medium">Future</th>
                </tr>
              </thead>
              <tbody>
                {data.twins_used.map((tw, i) => (
                  <tr key={tw.region_id} className={`border-b border-slate-700/30 ${i % 2 ? 'bg-slate-800/30' : ''}`}>
                    <td className="py-1.5 px-2 font-mono text-primary-400">#{tw.rank}</td>
                    <td className="py-1.5 px-2 font-mono text-slate-300">Lake {tw.lake_id}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-400">{tw.matched_year}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-300">{(tw.similarity_score * 100).toFixed(1)}%</td>
                    <td className="py-1.5 px-2 text-right font-mono text-cyan-400">{(tw.fixed_weight * 100).toFixed(0)}%</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-400">{tw.future_window.length}yr</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {data.audit_report && (
        <div className="rounded-xl bg-surface-800 border border-slate-700/60 overflow-hidden">
          <button
            onClick={() => setReportExpanded((v) => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span className="font-medium flex items-center gap-1.5">
              <Info className="h-3 w-3" />
              Forecast Reasoning
            </span>
            {reportExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {reportExpanded && (
            <div className="px-3 pb-3 space-y-2.5 text-[11px] leading-relaxed">
              <div className="rounded-lg bg-blue-950/30 border border-blue-800/20 p-2.5">
                <p className="font-semibold text-blue-300 mb-1">Summary</p>
                <p className="text-blue-200/80">{data.audit_report.summary}</p>
              </div>
              <div className="rounded-lg bg-surface-900/60 border border-slate-700/30 p-2.5">
                <p className="font-semibold text-slate-300 mb-1">Anchor</p>
                <p className="text-slate-400">{data.audit_report.anchor_details}</p>
              </div>
              <div className="rounded-lg bg-surface-900/60 border border-slate-700/30 p-2.5">
                <p className="font-semibold text-slate-300 mb-1">Weight Scheme</p>
                <p className="text-slate-400">{data.audit_report.weight_scheme}</p>
              </div>
              <div className="rounded-lg bg-surface-900/60 border border-slate-700/30 p-2.5">
                <p className="font-semibold text-slate-300 mb-1">Classification Rule</p>
                <p className="text-slate-400">{data.audit_report.classification_rule}</p>
              </div>
              {data.audit_report.twin_details.length > 0 && (
                <div className="rounded-lg bg-surface-900/60 border border-slate-700/30 p-2.5">
                  <p className="font-semibold text-slate-300 mb-1">Twin Details</p>
                  <ul className="space-y-1 text-slate-400">
                    {data.audit_report.twin_details.map((d, i) => (
                      <li key={i} className="pl-2 border-l-2 border-slate-700">{d}</li>
                    ))}
                  </ul>
                </div>
              )}
              {data.audit_report.per_year_reasoning.length > 0 && (
                <div className="rounded-lg bg-purple-950/20 border border-purple-800/20 p-2.5">
                  <p className="font-semibold text-purple-300 mb-1">Per-Year Analysis</p>
                  <ul className="space-y-1 text-purple-200/80">
                    {data.audit_report.per_year_reasoning.map((r, i) => (
                      <li key={i} className="pl-2 border-l-2 border-purple-700/40">{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

