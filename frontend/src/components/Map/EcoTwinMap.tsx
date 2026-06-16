import { useCallback, useEffect, useRef, useState } from 'react';
import {
  MapContainer,
  TileLayer,
  Rectangle,
  CircleMarker,
  Tooltip,
  Popup,
  useMapEvents,
  ZoomControl,
} from 'react-leaflet';
import type { LatLngBoundsLiteral, LatLngExpression } from 'leaflet';
import type { Feature, GeoJsonObject } from 'geojson';
import { ArrowLeft, MapPin, RefreshCw } from 'lucide-react';

import { queryRegionByCoords } from '@/api/regions';
import { useMapStore } from '@/store/mapStore';
import { useSimilarity } from '@/hooks/useSimilarity';
import { useSyncedStates } from '@/hooks/useSyncedStates';
import IndiaStateLayer from './IndiaStateLayer';
import type { AnalogResult } from '@/types';

// GeoJSON source: India state boundaries
const INDIA_GEOJSON_URL =
  'https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson';

// ── Constants ─────────────────────────────────────────────────────────────
const DEFAULT_CENTER: LatLngExpression = [
  Number(import.meta.env.VITE_MAP_DEFAULT_LAT ?? 20.5937),
  Number(import.meta.env.VITE_MAP_DEFAULT_LNG ?? 78.9629),
];
const DEFAULT_ZOOM = Number(import.meta.env.VITE_MAP_DEFAULT_ZOOM ?? 5);
const CELL_HALF_DEG = 5 / (2 * 111); // ~5 km in degrees

// ── Helpers ───────────────────────────────────────────────────────────────
function cellBounds(lat: number, lon: number): LatLngBoundsLiteral {
  return [
    [lat - CELL_HALF_DEG, lon - CELL_HALF_DEG],
    [lat + CELL_HALF_DEG, lon + CELL_HALF_DEG],
  ];
}

function similarityColor(score: number): string {
  if (score >= 0.85) return '#22c55e'; // emerald
  if (score >= 0.70) return '#84cc16'; // lime
  if (score >= 0.55) return '#eab308'; // yellow
  if (score >= 0.40) return '#f97316'; // orange
  return '#ef4444';                    // red
}

function fmt(n: number, d = 4) {
  return n.toFixed(d);
}

// ── Internal: click handler ───────────────────────────────────────────────
// Only active when user is in state drill-down mode (enabled=true)
function MapClickHandler({ enabled }: { enabled: boolean }) {
  const { selectRegion, setMapClickLoading, setActiveTab } = useMapStore();
  const [clickPos, setClickPos] = useState<{ lat: number; lon: number } | null>(null);

  useMapEvents({
    click: async (e) => {
      if (!enabled) return;
      const { lat, lng: lon } = e.latlng;
      setClickPos({ lat, lon });
      setMapClickLoading(true);
      try {
        const result = await queryRegionByCoords(lat, lon);
        selectRegion(result.region_id, result.center_lat, result.center_lon);
        setActiveTab('overview');
      } catch (err) {
        console.error('Region lookup failed:', err);
      } finally {
        setMapClickLoading(false);
        setClickPos(null);
      }
    },
  });

  // Show a pulsing dot at click position while loading
  if (!clickPos) return null;
  return (
    <CircleMarker
      center={[clickPos.lat, clickPos.lon]}
      radius={8}
      pathOptions={{
        color: '#22c55e',
        fillColor: '#22c55e',
        fillOpacity: 0.4,
        weight: 2,
        opacity: 0.9,
      }}
    />
  );
}

// ── Internal: selected region layer ──────────────────────────────────────
function SelectedRegionLayer({
  lat,
  lon,
}: {
  lat: number;
  lon: number;
}) {
  const bounds = cellBounds(lat, lon);
  return (
    <>
      {/* Outer highlight */}
      <Rectangle
        bounds={bounds}
        pathOptions={{
          color: '#22c55e',
          weight: 2.5,
          opacity: 0.9,
          fillColor: '#22c55e',
          fillOpacity: 0.08,
          dashArray: '6 4',
        }}
      />
      {/* Center dot */}
      <CircleMarker
        center={[lat, lon]}
        radius={5}
        pathOptions={{
          color: '#22c55e',
          fillColor: '#22c55e',
          fillOpacity: 1,
          weight: 2,
        }}
      >
        <Tooltip permanent direction="top" offset={[0, -8]} className="!bg-transparent !border-none !shadow-none">
          <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-xs text-white font-medium">
            Selected
          </span>
        </Tooltip>
      </CircleMarker>
    </>
  );
}

// ── Internal: analog markers layer ───────────────────────────────────────
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
      {analogs.map((analog, i) => {
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
                  <span className="font-semibold text-slate-100 text-sm">
                    Analog #{i + 1}
                  </span>
                  <span
                    className="rounded-full px-1.5 py-0.5 text-xs font-bold"
                    style={{ background: color + '33', color }}
                  >
                    {(analog.similarity_score * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="font-mono text-[11px] text-slate-400 break-all">
                  {analog.region_id.slice(0, 16)}…
                </p>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-300">
                  <span className="text-slate-500">Lat</span>
                  <span>{fmt(analog.center_lat)}</span>
                  <span className="text-slate-500">Lon</span>
                  <span>{fmt(analog.center_lon)}</span>
                  <span className="text-slate-500">Year</span>
                  <span>{analog.year}</span>
                  {analog.dominant_ecosystem && (
                    <>
                      <span className="text-slate-500">Eco</span>
                      <span className="capitalize">{analog.dominant_ecosystem}</span>
                    </>
                  )}
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

// ── Main map component ────────────────────────────────────────────────────
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

  const { data: similarityData } = useSimilarity(selectedRegionId, topK);
  const { data: syncedStates = [] } = useSyncedStates();

  // ── State: selected Indian state for drill-down ────────────────────────
  const [activeState, setActiveState] = useState<string | null>(null);

  const [geoJson, setGeoJson] = useState<GeoJsonObject | null>(null);
  const [geoJsonError, setGeoJsonError] = useState(false);
  const geoJsonFetched = useRef(false);

  // Fetch India GeoJSON once
  useEffect(() => {
    if (geoJsonFetched.current) return;
    geoJsonFetched.current = true;
    fetch(INDIA_GEOJSON_URL)
      .then((r) => r.json())
      .then((data: GeoJsonObject) => setGeoJson(data))
      .catch(() => setGeoJsonError(true));
  }, []);

  const handleAnalogClick = useCallback(
    (analog: AnalogResult) => {
      selectRegion(analog.region_id, analog.center_lat, analog.center_lon);
      setActiveTab('overview');
    },
    [selectRegion, setActiveTab],
  );

  const handleStateSelect = useCallback((canonical: string, _feature: Feature) => {
    setActiveState(canonical);
    // IndiaStateLayer handles fitBounds internally via useEffect
  }, []);

  const handleBackToIndia = () => {
    setActiveState(null);
  };

  const inStateMode = activeState !== null;
  const noDataAvailable = syncedStates.length === 0;

  return (
    <div className="relative h-full w-full">

      {/* ── Map loading overlay ── */}
      {mapClickLoading && (
        <div className="absolute inset-x-0 top-3 z-[1000] flex justify-center">
          <div className="flex items-center gap-2 rounded-full bg-surface-800/90 px-4 py-2 shadow-xl backdrop-blur-sm border border-slate-700/50">
            <span className="h-2 w-2 rounded-full bg-primary-400 animate-ping" />
            <span className="text-xs text-slate-300">Finding nearest region…</span>
          </div>
        </div>
      )}

      {/* ── Back button + state name (drill-down mode) ── */}
      {inStateMode && (
        <div className="absolute top-4 left-4 z-[1000] flex items-center gap-2">
          <button
            onClick={handleBackToIndia}
            className="flex items-center gap-1.5 rounded-lg bg-surface-800/90 border border-slate-700/50 px-3 py-2 text-xs font-medium text-slate-200 backdrop-blur-sm hover:bg-surface-700/90 transition-colors shadow-lg"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to India
          </button>
          <div className="rounded-lg bg-sky-500/20 border border-sky-500/40 px-3 py-2 text-xs font-semibold text-sky-300 backdrop-blur-sm shadow-lg">
            {activeState}
          </div>
        </div>
      )}

      {/* ── Drill-down click hint ── */}
      {inStateMode && !selectedRegionId && !mapClickLoading && (
        <div className="pointer-events-none absolute bottom-8 left-1/2 z-[1000] -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-full bg-surface-800/80 px-4 py-2 border border-sky-500/40 backdrop-blur-sm">
            <MapPin className="h-3.5 w-3.5 text-sky-400" />
            <span className="text-xs text-slate-300">
              Click within <span className="text-sky-300 font-medium">{activeState}</span> to select a point
            </span>
          </div>
        </div>
      )}

      {/* ── Overview: no data banner ── */}
      {!inStateMode && noDataAvailable && !geoJsonError && (
        <div className="pointer-events-none absolute bottom-6 left-1/2 z-[1000] -translate-x-1/2 w-max">
          <div className="flex items-center gap-2.5 rounded-xl bg-surface-800/90 border border-slate-600/50 px-5 py-3 backdrop-blur-sm shadow-xl">
            <RefreshCw className="h-4 w-4 flex-shrink-0 text-slate-400" />
            <span className="text-sm text-slate-300">
              No state data available —{' '}
              <span className="text-primary-400 font-medium">Sync data first</span>{' '}
              using the Sync button in the toolbar
            </span>
          </div>
        </div>
      )}

      {/* ── Overview: select a state hint (when states have data) ── */}
      {!inStateMode && !noDataAvailable && !selectedRegionId && !mapClickLoading && (
        <div className="pointer-events-none absolute bottom-8 left-1/2 z-[1000] -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-full bg-surface-800/80 px-4 py-2 border border-teal-500/30 backdrop-blur-sm">
            <span className="h-2 w-2 rounded-full bg-teal-400 flex-shrink-0" />
            <span className="text-xs text-slate-300">
              Click a highlighted state to start exploring
            </span>
          </div>
        </div>
      )}

      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        zoomControl={false}
        className="h-full w-full"
        preferCanvas={false}
      >
        {/* Satellite basemap */}
        <TileLayer
          attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          maxZoom={18}
        />

        {/* Labels layer on top of satellite */}
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
          opacity={0.7}
          maxZoom={18}
        />

        <ZoomControl position="bottomright" />

        {/* India state boundaries layer */}
        {geoJson && (
          <IndiaStateLayer
            geoData={geoJson}
            syncedStates={syncedStates}
            activeState={activeState}
            onStateSelect={handleStateSelect}
          />
        )}

        {/* Region click handler — only active in state drill-down mode */}
        <MapClickHandler enabled={inStateMode} />

        {/* Selected region */}
        {selectedRegionLat !== null && selectedRegionLon !== null && (
          <SelectedRegionLayer
            lat={selectedRegionLat}
            lon={selectedRegionLon}
          />
        )}

        {/* Analog regions */}
        {similarityData && similarityData.analogs.length > 0 && (
          <AnalogLayer
            analogs={similarityData.analogs}
            highlightedId={highlightedAnalogId}
            onHover={setHighlightedAnalogId}
            onClick={handleAnalogClick}
          />
        )}
      </MapContainer>

      {/* Similarity legend */}
      {similarityData && similarityData.analogs.length > 0 && (
        <div className="absolute bottom-8 right-12 z-[1000] rounded-lg bg-surface-800/90 backdrop-blur-sm border border-slate-700/50 p-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Similarity
          </p>
          {[
            { label: '≥ 85%', color: '#22c55e' },
            { label: '70–85%', color: '#84cc16' },
            { label: '55–70%', color: '#eab308' },
            { label: '40–55%', color: '#f97316' },
            { label: '< 40%', color: '#ef4444' },
          ].map(({ label, color }) => (
            <div key={label} className="flex items-center gap-2 mb-0.5">
              <span
                className="h-2.5 w-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-[10px] text-slate-300">{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
