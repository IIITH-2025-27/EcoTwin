import { Copy, Check, MapPin } from 'lucide-react';
import { useState } from 'react';
import { clsx } from 'clsx';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import Badge from '@/components/common/Badge';
import Card from '@/components/common/Card';
import { useRegion } from '@/hooks/useRegion';
import { useMapStore } from '@/store/mapStore';

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
    </div>
  );
}
