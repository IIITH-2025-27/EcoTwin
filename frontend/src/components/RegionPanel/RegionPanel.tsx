import { Copy, Check, MapPin } from 'lucide-react';
import { useState } from 'react';
import { clsx } from 'clsx';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import Badge from '@/components/common/Badge';
import Card from '@/components/common/Card';
import { useRegion } from '@/hooks/useRegion';
import { useMapStore } from '@/store/mapStore';
import type { RegionFeature } from '@/types';

// ── Indicator bar ─────────────────────────────────────────────────────────
function IndicatorBar({
  label,
  value,
  min = -1,
  max = 1,
  color,
}: {
  label: string;
  value: number | null | undefined;
  min?: number;
  max?: number;
  color: string;
}) {
  if (value === null || value === undefined) {
    return (
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500">{label}</span>
        <span className="text-slate-600">—</span>
      </div>
    );
  }

  const pct = Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-mono font-medium text-slate-200">
          {value.toFixed(3)}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-slate-700/60">
        <div
          className="h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ── Copy UUID button ──────────────────────────────────────────────────────
function CopyId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="ml-1 rounded p-0.5 text-slate-500 hover:text-slate-300 transition-colors"
      title="Copy region ID"
    >
      {copied ? (
        <Check className="h-3 w-3 text-primary-400" />
      ) : (
        <Copy className="h-3 w-3" />
      )}
    </button>
  );
}

// ── Main component ────────────────────────────────────────────────────────
export default function RegionPanel() {
  const { selectedRegionId } = useMapStore();
  const { data, isLoading, error, refetch } = useRegion(selectedRegionId);

  if (!selectedRegionId) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center px-4">
        <MapPin className="h-10 w-10 text-slate-700" />
        <p className="text-sm font-medium text-slate-400">No region selected</p>
        <p className="text-xs text-slate-600">
          Click anywhere on the map to select an ecosystem region
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" label="Loading region data…" />
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

  const { region, latest_features: f } = data;

  return (
    <div className="space-y-3 p-3 tab-content-enter">
      {/* Region identity */}
      <Card>
        <div className="space-y-2.5">
          <div className="flex items-start justify-between">
            <div>
              {region.name && (
                <p className="text-sm font-semibold text-slate-100 mb-0.5">{region.name}</p>
              )}
              {region.country && (
                <p className="text-[11px] text-slate-400">
                  {region.state ? `${region.state}, ` : ''}{region.country}
                </p>
              )}
            </div>
            {f?.dominant_ecosystem && (
              <Badge
                label={f.dominant_ecosystem}
                variant="success"
                className="capitalize"
              />
            )}
          </div>

          <div className="space-y-1 pt-1">
            <p className="text-xs text-slate-500">Region ID</p>
            <div className="flex items-center">
              <span className="font-mono text-xs text-slate-300">
                {region.region_id.slice(0, 18)}…
              </span>
              <CopyId id={region.region_id} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-slate-500">Latitude</p>
              <p className="font-mono text-sm text-slate-200">
                {region.center_lat.toFixed(5)}°
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Longitude</p>
              <p className="font-mono text-sm text-slate-200">
                {region.center_lon.toFixed(5)}°
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Area</p>
              <p className="text-sm text-slate-200">
                {region.area_sqkm != null ? `${region.area_sqkm.toFixed(2)} km²` : '—'}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Last Year</p>
              <p className="text-sm text-slate-200">{region.year ?? '—'}</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Environmental indicators */}
      {f ? (
        <Card title="Environmental Indicators" subtitle={`Year ${f.year}`}>
          <div className="space-y-3.5">
            <IndicatorBar
              label="NDVI (Vegetation)"
              value={f.ndvi_mean}
              color="#22c55e"
            />
            <IndicatorBar
              label="NDWI (Water)"
              value={f.ndwi_mean}
              color="#3b82f6"
            />
            <IndicatorBar
              label="NBR (Burn Severity)"
              value={f.nbr_mean}
              color="#f97316"
            />
            {(f.ndvi_std !== null || f.ndwi_std !== null) && (
              <div className="border-t border-slate-700/40 pt-3 space-y-2">
                <p className="text-xs text-slate-500 uppercase tracking-wider">
                  Std Deviation
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { label: 'NDVI σ', value: f.ndvi_std },
                    { label: 'NDWI σ', value: f.ndwi_std },
                    { label: 'NBR σ', value: f.nbr_std },
                  ].map(({ label, value }) => (
                    <div key={label} className="text-center">
                      <p className="text-[10px] text-slate-500">{label}</p>
                      <p className="font-mono text-xs text-slate-300">
                        {value !== null && value !== undefined
                          ? value.toFixed(3)
                          : '—'}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      ) : (
        <Card>
          <p className="text-center text-sm text-slate-500">
            No indicator data available for this region.
          </p>
        </Card>
      )}
    </div>
  );
}
