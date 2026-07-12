import { useCallback, useEffect, useRef, useState } from 'react';
import { clsx } from 'clsx';
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  ZoomControl,
} from 'react-leaflet';
import { geoJSON } from 'leaflet';
import type { LatLngExpression } from 'leaflet';
import type { Feature, GeoJsonObject } from 'geojson';
import { Loader2 } from 'lucide-react';

import { useRegions } from '@/hooks/useRegions';
import { useMapStore } from '@/store/mapStore';
import { useSimilarity } from '@/hooks/useSimilarity';
import { getActiveLakeMarkers, getLakeGeometry } from '@/api/regions';
import type { LakeMarker } from '@/api/regions';
import type { AnalogResult, LakeGeometry, LakeRegionResponse, LakeSearchResult } from '@/types';
import LakeSearch from './LakeSearch';

const DEFAULT_CENTER: LatLngExpression = [20.5937, 78.9629];
const DEFAULT_ZOOM = 5;
const INDIA_BOUNDS: [[number, number], [number, number]] = [[6.0, 68.0], [38.5, 98.5]];

function similarityColor(score: number): string {
  if (score >= 0.85) return '#22c55e';
  if (score >= 0.70) return '#84cc16';
  if (score >= 0.55) return '#eab308';
  if (score >= 0.40) return '#f97316';
  return '#ef4444';
}

function fmt(n: number, d = 4) {
  return n.toFixed(d);
}

function toGeoJson(region: LakeRegionResponse): Feature {
  if (region.geometry) {
    return {
      type: 'Feature',
      properties: { ...region },
      geometry: region.geometry,
    } as Feature;
  }

  if (region.bbox) {
    const { minX, minY, maxX, maxY } = region.bbox as Record<string, number>;
    return {
      type: 'Feature',
      properties: { ...region },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [minX, minY],
          [maxX, minY],
          [maxX, maxY],
          [minX, maxY],
          [minX, minY],
        ]],
      },
    } as Feature;
  }

  return {
    type: 'Feature',
    properties: { ...region },
    geometry: null,
  } as unknown as Feature;
}

// ── Active Lake Markers ──────────────────────────────────────────────────────

function ActiveLakeMarkers({
  lakes,
  activeLakeId,
  onSelect,
}: {
  lakes: LakeMarker[];
  activeLakeId: number | null;
  onSelect: (lake: LakeMarker) => void;
}) {
  return (
    <>
      {lakes.map((lake) => {
        const isActive = lake.lake_id === activeLakeId;
        return (
          <CircleMarker
            key={lake.lake_id}
            center={[lake.center_lat, lake.center_lon]}
            radius={isActive ? 6 : 4}
            pathOptions={{
              color: isActive ? '#fde047' : '#22d3ee',
              fillColor: isActive ? '#fde047' : '#06b6d4',
              fillOpacity: isActive ? 0.9 : 0.65,
              weight: isActive ? 2 : 1.5,
            }}
            eventHandlers={{
              click: () => onSelect(lake),
            }}
          >
            <Tooltip
              sticky
              className="!bg-transparent !border-none !shadow-none"
            >
              <div className="rounded-lg bg-slate-900/95 px-2.5 py-1.5 shadow-xl border border-slate-700/60 min-w-[120px]">
                <p className="text-xs font-semibold text-slate-100 truncate max-w-[160px]">
                  {lake.display_name}
                </p>
                {lake.state && (
                  <p className="text-[10px] text-slate-400 mt-0.5">{lake.state}</p>
                )}
                {lake.area_sqkm !== null && (
                  <p className="text-[10px] text-cyan-400 mt-0.5">
                    {lake.area_sqkm.toFixed(2)} km²
                  </p>
                )}
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

// ── Region / sub-region layer ─────────────────────────────────────────────────

function LakeRegionLayer({
  regions,
  selectedRegionId,
  onSelect,
}: {
  regions: LakeRegionResponse[];
  selectedRegionId: string | null;
  onSelect: (region: LakeRegionResponse) => void;
}) {
  return (
    <>
      {regions.map((region) => {
        const isSelected = region.region_id === selectedRegionId;
        const feature = toGeoJson(region);
        return (
          <GeoJSON
            key={region.region_id}
            data={feature as GeoJsonObject}
            style={() => ({
              color: isSelected ? '#38bdf8' : '#14b8a6',
              weight: isSelected ? 3 : 1.25,
              fillColor: isSelected ? '#38bdf8' : '#14b8a6',
              fillOpacity: isSelected ? 0.35 : 0.18,
              opacity: 0.9,
            })}
            eventHandlers={{
              click: () => onSelect(region),
            }}
          >
            <Popup>
              <div className="space-y-1 min-w-[180px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-100 text-sm">{region.name}</span>
                  <span className="rounded-full px-1.5 py-0.5 text-[10px] font-bold text-primary-300">
                    Lake
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-300">
                  <span className="text-slate-500">ID</span>
                  <span className="font-mono text-[11px]">{region.hydrolake_id}</span>
                  <span className="text-slate-500">Area</span>
                  <span>{region.area_sqkm.toFixed(2)} km²</span>
                  <span className="text-slate-500">Lat</span>
                  <span>{fmt(region.center_lat)}</span>
                  <span className="text-slate-500">Lon</span>
                  <span>{fmt(region.center_lon)}</span>
                </div>
              </div>
            </Popup>
            <Tooltip sticky className="!bg-transparent !border-none !shadow-none">
              <span className="rounded bg-slate-900/90 px-2 py-1 text-xs text-slate-100 shadow-lg">
                {region.name}
              </span>
            </Tooltip>
          </GeoJSON>
        );
      })}
    </>
  );
}

// ── Selected region marker dot ────────────────────────────────────────────────

function SelectedRegionMarker({ lat, lon }: { lat: number; lon: number }) {
  return (
    <CircleMarker
      center={[lat, lon]}
      radius={6}
      pathOptions={{
        color: '#38bdf8',
        fillColor: '#38bdf8',
        fillOpacity: 1,
        weight: 2,
      }}
    >
      <Tooltip permanent direction="top" offset={[0, -8]} className="!bg-transparent !border-none !shadow-none">
        <span className="rounded bg-sky-600 px-1.5 py-0.5 text-xs font-medium text-white">Selected</span>
      </Tooltip>
    </CircleMarker>
  );
}

// ── Yellow lake polygon (search / marker click) ───────────────────────────────

function SelectedLakePolygon({ lake }: { lake: LakeGeometry }) {
  const map = useMap();

  useEffect(() => {
    if (lake.geometry) {
      const bounds = geoJSON(lake.geometry as GeoJsonObject).getBounds();
      if (bounds.isValid()) {
        map.flyToBounds(bounds, { padding: [48, 48], maxZoom: 12, duration: 0.8 });
        return;
      }
    }
    if (lake.center_lat !== null && lake.center_lon !== null) {
      map.flyTo([lake.center_lat, lake.center_lon], 11, { duration: 0.8 });
    }
  }, [lake, map]);

  if (!lake.geometry) return null;

  return (
    <GeoJSON
      data={lake.geometry as GeoJsonObject}
      style={() => ({
        color: '#fde047',
        weight: 5,
        fillColor: '#fde047',
        fillOpacity: 0.18,
        opacity: 1,
      })}
    >
      <Popup>
        <div className="min-w-[180px] space-y-1">
          <p className="text-sm font-semibold">{lake.display_name}</p>
          <p className="text-xs text-slate-600">{lake.state ?? lake.country}</p>
          {lake.area_sqkm !== null && <p className="text-xs text-slate-600">{lake.area_sqkm.toFixed(2)} km²</p>}
        </div>
      </Popup>
    </GeoJSON>
  );
}

// ── Analog markers ────────────────────────────────────────────────────────────

function AnalogLayer({
  analogs,
  highlightedId,
  onHover,
  onClick,
}: {
  analogs: AnalogResult[];
  highlightedId: string | null;
  onHover: (id: string | null) => void;
  onClick: (analog: AnalogResult) => void;
}) {
  return (
    <>
      {analogs.map((analog, index) => {
        const color = similarityColor(analog.similarity_score);
        const isHighlighted = analog.region_id === highlightedId;
        return (
          <CircleMarker
            key={analog.region_id}
            center={[analog.center_lat, analog.center_lon]}
            radius={isHighlighted ? 12 : 8}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: isHighlighted ? 0.8 : 0.5,
              weight: isHighlighted ? 3 : 1.5,
            }}
            eventHandlers={{
              mouseover: () => onHover(analog.region_id),
              mouseout: () => onHover(null),
              click: () => onClick(analog),
            }}
          >
            <Popup>
              <div className="space-y-1 min-w-[160px]">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-100 text-sm">Analog #{index + 1}</span>
                  <span className="rounded-full px-1.5 py-0.5 text-xs font-bold" style={{ background: color + '33', color }}>
                    {(analog.similarity_score * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="font-mono text-[11px] text-slate-400 break-all">{analog.region_id.slice(0, 16)}…</p>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-300">
                  <span className="text-slate-500">Lat</span>
                  <span>{fmt(analog.center_lat)}</span>
                  <span className="text-slate-500">Lon</span>
                  <span>{fmt(analog.center_lon)}</span>
                  <span className="text-slate-500">Year</span>
                  <span>{analog.year}</span>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

// ── Main map ──────────────────────────────────────────────────────────────────

export default function EcoTwinMap() {
  const {
    selectedRegionId,
    selectedRegionLat,
    selectedRegionLon,
    topK,
    highlightedAnalogId,
    mapClickLoading,
    setHighlightedAnalogId,
    selectRegion,
    setActiveTab,
  } = useMapStore();

  const { data: regions = [] } = useRegions('India');
  const { data: similarityData } = useSimilarity(selectedRegionId, topK);

  // ── Selected lake polygon (from search or marker click) ──────────────────
  const [selectedLake, setSelectedLake] = useState<LakeGeometry | null>(null);
  const [activeLakeId, setActiveLakeId] = useState<number | null>(null);
  const [lakeSearchError, setLakeSearchError] = useState<string | null>(null);
  const [lakeLoading, setLakeLoading] = useState(false);
  const lakeRequestId = useRef(0);

  // ── Active lake markers ──────────────────────────────────────────────────
  const [lakeMarkers, setLakeMarkers] = useState<LakeMarker[]>([]);
  const [showLakeMarkers, setShowLakeMarkers] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getActiveLakeMarkers('India')
      .then((markers) => { if (!cancelled) setLakeMarkers(markers); })
      .catch(() => { /* silently ignore — markers are optional UI enhancement */ });
    return () => { cancelled = true; };
  }, []);

  // ── Shared handler: load geometry and highlight lake ─────────────────────
  const loadLakeGeometry = useCallback(async (lakeId: number) => {
    const reqId = ++lakeRequestId.current;
    setSelectedLake(null);
    setActiveLakeId(lakeId);
    setLakeSearchError(null);
    setLakeLoading(true);
    try {
      const geo = await getLakeGeometry(lakeId);
      if (lakeRequestId.current === reqId) {
        setSelectedLake(geo);
      }
    } catch (err) {
      if (lakeRequestId.current === reqId) {
        setLakeSearchError(err instanceof Error ? err.message : 'Could not load lake polygon.');
        setActiveLakeId(null);
      }
    } finally {
      if (lakeRequestId.current === reqId) setLakeLoading(false);
    }
  }, []);

  const handleRegionSelect = useCallback(
    (region: LakeRegionResponse) => {
      selectRegion(region.region_id, region.center_lat, region.center_lon);
      setActiveTab('overview');
    },
    [selectRegion, setActiveTab],
  );

  const handleAnalogClick = useCallback(
    (analog: AnalogResult) => {
      selectRegion(analog.region_id, analog.center_lat, analog.center_lon);
      setActiveTab('overview');
    },
    [selectRegion, setActiveTab],
  );

  /** Called when user picks a lake from the search bar */
  const handleLakeSearchSelect = useCallback((lake: LakeSearchResult) => {
    void loadLakeGeometry(lake.lake_id);
  }, [loadLakeGeometry]);

  /** Called when user clicks a lake marker pin */
  const handleMarkerClick = useCallback((lake: LakeMarker) => {
    void loadLakeGeometry(lake.lake_id);
  }, [loadLakeGeometry]);

  const isLoadingGeometry = lakeLoading || mapClickLoading;

  return (
    <div className="relative h-full w-full">
      {/* Search bar */}
      <LakeSearch onSelect={handleLakeSearchSelect} />

      {/* Loading indicator */}
      {isLoadingGeometry && (
        <div className="absolute inset-x-0 top-16 z-[1000] flex justify-center">
          <div className="flex items-center gap-2 rounded-full border border-slate-700/50 bg-surface-800/90 px-4 py-2 shadow-xl backdrop-blur-sm">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />
            <span className="text-xs text-slate-300">Loading lake boundary…</span>
          </div>
        </div>
      )}

      {/* Error */}
      {lakeSearchError && (
        <div className="absolute left-1/2 top-16 z-[1000] -translate-x-1/2 rounded-md bg-rose-950/95 px-3 py-2 text-xs text-rose-200 shadow-lg">
          {lakeSearchError}
        </div>
      )}

      {/* Hint */}
      {!selectedRegionId && !isLoadingGeometry && (
        <div className="pointer-events-none absolute bottom-8 left-1/2 z-[1000] -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-full border border-cyan-500/30 bg-surface-800/80 px-4 py-2 backdrop-blur-sm">
            <span className="h-2 w-2 flex-shrink-0 rounded-full bg-cyan-400" />
            <span className="text-xs text-slate-300">
              Click a lake marker or search to explore its ecosystem profile
            </span>
          </div>
        </div>
      )}

      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        minZoom={4}
        maxZoom={14}
        maxBounds={INDIA_BOUNDS}
        maxBoundsViscosity={1.0}
        zoomControl={false}
        className="h-full w-full"
        preferCanvas={false}
      >
        {/* Satellite imagery */}
        <TileLayer
          attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          maxZoom={18}
        />
        {/* Labels overlay */}
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
          opacity={0.7}
          maxZoom={18}
        />

        <ZoomControl position="bottomright" />

        {/* Sub-region GeoJSON polygons */}
        <LakeRegionLayer
          regions={regions}
          selectedRegionId={selectedRegionId}
          onSelect={handleRegionSelect}
        />

        {/* Active lake centroid markers — only when checkbox is on */}
        {showLakeMarkers && (
          <ActiveLakeMarkers
            lakes={lakeMarkers}
            activeLakeId={activeLakeId}
            onSelect={handleMarkerClick}
          />
        )}

        {/* Yellow highlighted lake boundary */}
        {selectedLake && <SelectedLakePolygon lake={selectedLake} />}

        {/* Blue dot for selected sub-region */}
        {selectedRegionLat !== null && selectedRegionLon !== null && (
          <SelectedRegionMarker lat={selectedRegionLat} lon={selectedRegionLon} />
        )}

        {/* Analog markers */}
        {similarityData && similarityData.analogs.length > 0 && (
          <AnalogLayer
            analogs={similarityData.analogs}
            highlightedId={highlightedAnalogId}
            onHover={setHighlightedAnalogId}
            onClick={handleAnalogClick}
          />
        )}
      </MapContainer>

      {/* Layer legend + Show Lakes toggle */}
      <div className="absolute bottom-8 left-4 z-[1000] rounded-lg border border-slate-700/50 bg-surface-800/90 p-3 backdrop-blur-sm">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Map Layers</p>
        <div className="space-y-1.5">

          {/* Show Lakes checkbox */}
          <label
            htmlFor="toggle-lake-markers"
            className="flex cursor-pointer items-center gap-2 select-none"
          >
            <div className="relative flex items-center">
              <input
                id="toggle-lake-markers"
                type="checkbox"
                checked={showLakeMarkers}
                onChange={(e) => setShowLakeMarkers(e.target.checked)}
                className="sr-only"
              />
              {/* Custom checkbox track */}
              <div
                className={clsx(
                  'h-3.5 w-3.5 rounded-sm border transition-colors',
                  showLakeMarkers
                    ? 'border-cyan-500 bg-cyan-500'
                    : 'border-slate-500 bg-transparent',
                )}
              >
                {showLakeMarkers && (
                  <svg
                    viewBox="0 0 10 10"
                    className="h-full w-full text-slate-900"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="1.5,5 4,7.5 8.5,2" />
                  </svg>
                )}
              </div>
            </div>
            <span className={clsx('text-[10px]', showLakeMarkers ? 'text-cyan-300' : 'text-slate-400')}>
              Show Lakes
            </span>
            {showLakeMarkers && (
              <span className="h-2 w-2 flex-shrink-0 rounded-full border border-cyan-400 bg-cyan-500/60" />
            )}
          </label>

          {/* Selected lake dot */}
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 flex-shrink-0 rounded-full border border-yellow-400 bg-yellow-400/60" />
            <span className="text-[10px] text-slate-400">Selected Lake</span>
          </div>

          {/* Sub-region cell */}
          {regions.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 flex-shrink-0 rounded-sm border border-teal-400 bg-teal-500/25" />
              <span className="text-[10px] text-slate-400">Sub-region Cell</span>
            </div>
          )}
        </div>
      </div>

      {/* Similarity legend */}
      {similarityData && similarityData.analogs.length > 0 && (
        <div className="absolute bottom-8 right-12 z-[1000] rounded-lg border border-slate-700/50 bg-surface-800/90 p-3 backdrop-blur-sm">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Similarity</p>
          {[
            { label: '≥ 85%', color: '#22c55e' },
            { label: '70–85%', color: '#84cc16' },
            { label: '55–70%', color: '#eab308' },
            { label: '40–55%', color: '#f97316' },
            { label: '< 40%', color: '#ef4444' },
          ].map(({ label, color }) => (
            <div key={label} className="mb-0.5 flex items-center gap-2">
              <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full" style={{ backgroundColor: color }} />
              <span className="text-[10px] text-slate-300">{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
