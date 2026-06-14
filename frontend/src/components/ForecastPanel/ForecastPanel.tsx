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
import { TrendingUp, TrendingDown, Minus, Info } from 'lucide-react';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import Card from '@/components/common/Card';
import Badge, { trendToBadgeVariant } from '@/components/common/Badge';
import { useForecast } from '@/hooks/useForecast';
import { useTemporal } from '@/hooks/useTemporal';
import { useMapStore } from '@/store/mapStore';
import type { TrendDirection } from '@/types';

type IndicatorKey = 'ndvi' | 'ndwi' | 'nbr';

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
  const { selectedRegionId } = useMapStore();
  const [activeIndicator, setActiveIndicator] = useState<IndicatorKey>('ndvi');

  const { data: forecast, isLoading: fLoading, error: fError, refetch: fRefetch } =
    useForecast(selectedRegionId);
  const { data: temporal } = useTemporal(selectedRegionId);

  const ind = INDICATORS.find((i) => i.key === activeIndicator)!;

  const chartData = useMemo(() => {
    if (!forecast) return [];

    // Historical rows
    const historicalRows =
      temporal?.[activeIndicator]?.map((d) => ({
        year: d.year,
        historical: d.value,
        forecast: null as number | null,
        confidence_lo: null as number | null,
        confidence_hi: null as number | null,
      })) ?? [];

    // Forecast rows
    const forecastRows = forecast.forecast_horizons.map((h) => ({
      year: h.year,
      historical: null as number | null,
      forecast: h[ind.forecastKey],
      confidence_lo: h[ind.forecastKey] - (1 - h.confidence) * 0.15,
      confidence_hi: h[ind.forecastKey] + (1 - h.confidence) * 0.15,
    }));

    // Stitch: last historical point is duplicated as first forecast point
    const lastHist = historicalRows[historicalRows.length - 1];
    if (lastHist && forecastRows.length > 0) {
      forecastRows[0] = {
        ...forecastRows[0],
        historical: lastHist.historical,
      };
    }

    return [...historicalRows, ...forecastRows];
  }, [forecast, temporal, activeIndicator, ind]);

  const splitYear = forecast?.current_year;

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

  if (!forecast) return null;

  return (
    <div className="space-y-3 p-3 tab-content-enter">
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

      {/* Indicator selector */}
      <div className="flex gap-1">
        {INDICATORS.map((i) => (
          <button
            key={i.key}
            onClick={() => setActiveIndicator(i.key)}
            className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-all ${
              activeIndicator === i.key
                ? 'text-white'
                : 'bg-surface-800 text-slate-500 hover:text-slate-300'
            }`}
            style={
              activeIndicator === i.key
                ? { backgroundColor: i.color + '33', color: i.color, borderBottom: `2px solid ${i.color}` }
                : {}
            }
          >
            {i.label}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="rounded-xl bg-surface-800 border border-slate-700/60 p-4">
        <p className="mb-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {ind.label} — Historical + 5-Year Analog Forecast
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="year"
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={false}
            />
            <YAxis
              domain={[-1, 1]}
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />

            {/* Confidence band */}
            <Area
              type="monotone"
              dataKey="confidence_hi"
              stroke="none"
              fill={ind.color}
              fillOpacity={0.08}
              name="Confidence Hi"
              legendType="none"
              connectNulls
            />
            <Area
              type="monotone"
              dataKey="confidence_lo"
              stroke="none"
              fill="white"
              fillOpacity={0}
              name="Confidence Lo"
              legendType="none"
              connectNulls
            />

            {/* Historical line */}
            <Line
              type="monotone"
              dataKey="historical"
              name="Historical"
              stroke={ind.color}
              strokeWidth={2.5}
              dot={{ r: 3, fill: ind.color }}
              activeDot={{ r: 5 }}
              connectNulls
            />

            {/* Forecast line */}
            <Line
              type="monotone"
              dataKey="forecast"
              name="Forecast"
              stroke={ind.color}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3.5, fill: ind.color, opacity: 0.7 }}
              activeDot={{ r: 5 }}
              connectNulls
            />

            {/* Current year divider */}
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
      </div>

      {/* Forecast table */}
      <div className="rounded-xl bg-surface-800 border border-slate-700/60 overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700/60">
              <th className="py-2 px-3 text-left text-slate-500 font-medium">Year</th>
              <th className="py-2 px-3 text-right text-slate-500 font-medium">{ind.label}</th>
              <th className="py-2 px-3 text-right text-slate-500 font-medium">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {forecast.forecast_horizons.map((h, i) => (
              <tr
                key={h.year}
                className={`border-b border-slate-700/30 ${
                  i % 2 === 0 ? '' : 'bg-slate-800/30'
                }`}
              >
                <td className="py-2 px-3 font-mono text-slate-300">{h.year}</td>
                <td className="py-2 px-3 text-right font-mono text-slate-200">
                  {h[ind.forecastKey].toFixed(4)}
                </td>
                <td className="py-2 px-3 text-right">
                  <span
                    className={`font-medium ${
                      h.confidence >= 0.7
                        ? 'text-emerald-400'
                        : h.confidence >= 0.5
                        ? 'text-amber-400'
                        : 'text-red-400'
                    }`}
                  >
                    {(h.confidence * 100).toFixed(0)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Explanation */}
      <div className="rounded-lg bg-blue-950/30 border border-blue-800/30 p-3 flex gap-2">
        <Info className="h-3.5 w-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
        <p className="text-[11px] text-blue-300 leading-relaxed">
          {forecast.explanation}
        </p>
      </div>
    </div>
  );
}
