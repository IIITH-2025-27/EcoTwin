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
const EMPTY_REGIONS: LakeRegionResponse[] = [];

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

function formatYearRange(startYear: number, endYear: number): string {
  return startYear === endYear
    ? `Year ${startYear}`
    : `Years ${startYear} to ${endYear}`;
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
                  <span className="font-semibold text-slate-100 text-sm">{region.name ?? 'Lake'}</span>
                  <span className="rounded-full px-1.5 py-0.5 text-[10px] font-bold text-primary-300">
                    {region.year}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-300">
                  <span className="text-slate-500">ID</span>
                  <span className="font-mono text-[11px]">{region.hydrolake_id ?? region.lake_id}</span>
                  <span className="text-slate-500">Area</span>
                  <span>{region.area_sqkm != null ? `${region.area_sqkm.toFixed(2)} km²` : '—'}</span>
                  <span className="text-slate-500">Lat</span>
                  <span>{fmt(region.center_lat)}</span>
                  <span className="text-slate-500">Lon</span>
                  <span>{fmt(region.center_lon)}</span>
                </div>
              </div>
            </Popup>
            <Tooltip sticky className="!bg-transparent !border-none !shadow-none">
              <span className="rounded bg-slate-900/90 px-2 py-1 text-xs text-slate-100 shadow-lg">
                {region.name ?? `Lake ${region.lake_id}`}
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

function SelectedLakePolygon({ lake, focusRevision }: { lake: LakeGeometry; focusRevision: number }) {
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
  }, [lake, focusRevision, map]);

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

function FocusedAnalogPolygon({
  lake,
  analogs,
  onZoomOut,
}: {
  lake: LakeGeometry;
  analogs: AnalogResult[];
  onZoomOut: () => void;
}) {
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
    <>
      <GeoJSON
        data={lake.geometry as GeoJsonObject}
        style={() => ({
          color: '#22c55e',
          weight: 4,
          fillColor: '#22c55e',
          fillOpacity: 0.16,
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

      <div className="absolute right-4 bottom-24 z-[1000]">
        <button
          type="button"
          onClick={() => {
            if (analogs.length === 1) {
              const [onlyAnalog] = analogs;
              map.flyTo([onlyAnalog.center_lat, onlyAnalog.center_lon], 8, { animate: true });
            } else if (analogs.length > 1) {
              const bounds: [number, number][] = analogs.map((analog) => [analog.center_lat, analog.center_lon]);
              map.fitBounds(bounds, { padding: [48, 48], maxZoom: 8, animate: true });
            }
            onZoomOut();
          }}
          className="rounded-full border border-emerald-400/30 bg-surface-800/90 px-3 py-2 text-xs font-medium text-emerald-200 shadow-xl backdrop-blur-sm transition-colors hover:border-emerald-300/60 hover:text-emerald-100"
        >
          Zoom out
        </button>
      </div>
    </>
  );
}

function MapTabEffects({
  activeTab,
  analogs,
}: {
  activeTab: string;
  analogs: AnalogResult[];
}) {
  const map = useMap();

  useEffect(() => {
    if (activeTab === 'analogs' && analogs.length > 0) {
      if (analogs.length === 1) {
        const [onlyAnalog] = analogs;
        map.flyTo([onlyAnalog.center_lat, onlyAnalog.center_lon], 8, { animate: true });
        return;
      }

      const bounds: [number, number][] = analogs.map((analog) => [analog.center_lat, analog.center_lon]);
      map.fitBounds(bounds, { padding: [48, 48], maxZoom: 8, animate: true });
    }
  }, [activeTab, analogs, map]);

  return null;
}

// ── Analog markers ────────────────────────────────────────────────────────────

function AnalogLayer({
  analogs,
  highlightedId,
  activeId,
  onHover,
  onClick,
}: {
  analogs: AnalogResult[];
  highlightedId: string | null;
  activeId: string | null;
  onHover: (id: string | null) => void;
  onClick: (analog: AnalogResult) => void;
}) {
  return (
    <>
      {analogs.map((analog, index) => {
        const color = similarityColor(analog.similarity_score);
        const isHighlighted = analog.region_id === highlightedId;
        const isActive = analog.region_id === activeId;
        return (
          <CircleMarker
            key={analog.region_id}
            center={[analog.center_lat, analog.center_lon]}
            radius={isHighlighted || isActive ? 12 : 8}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: isHighlighted || isActive ? 0.85 : 0.5,
              weight: isHighlighted || isActive ? 3 : 1.5,
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
                  <span className="text-slate-500">Window</span>
                  <span>{formatYearRange(analog.start_year, analog.end_year)}</span>
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
    activeTab,
    topK,
    highlightedAnalogId,
    focusedAnalogRegionId,
    focusedAnalogFocusRevision,
    mapClickLoading,
    selectedLake,
    selectedLakeFocusRevision,
    setHighlightedAnalogId,
    setFocusedAnalogRegionId,
    setMapClickLoading,
    selectRegion,
    setActiveTab,
    setSelectedLake,
    clearRegion,
  } = useMapStore();

  const { data: regions = EMPTY_REGIONS, isLoading: isLoadingRegions } = useRegions('India');
  const { data: similarityData } = useSimilarity(selectedRegionId, topK);

  const [activeLakeId, setActiveLakeId] = useState<number | null>(null);
  const [selectedLakeQuery, setSelectedLakeQuery] = useState('');
  const [committedLakeQuery, setCommittedLakeQuery] = useState<string | null>(null);
  const [lakeSearchError, setLakeSearchError] = useState<string | null>(null);
  const [lakeLoading, setLakeLoading] = useState(false);
  const lakeRequestId = useRef(0);

  // ── Active lake markers ──────────────────────────────────────────────────
  const [lakeMarkers, setLakeMarkers] = useState<LakeMarker[]>([]);
  const [isLoadingLakeMarkers, setIsLoadingLakeMarkers] = useState(true);
  const [showLakeMarkers, setShowLakeMarkers] = useState(false);
  const [focusedAnalogLake, setFocusedAnalogLake] = useState<LakeGeometry | null>(null);

  useEffect(() => {
    if (activeTab === 'analogs') {
      setShowLakeMarkers(false);
    }
  }, [activeTab, setShowLakeMarkers]);

  useEffect(() => {
    let cancelled = false;
    getActiveLakeMarkers('India')
      .then((markers) => { if (!cancelled) setLakeMarkers(markers); })
      .catch(() => { /* silently ignore — markers are optional UI enhancement */ })
      .finally(() => { if (!cancelled) setIsLoadingLakeMarkers(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (!focusedAnalogRegionId) {
      setFocusedAnalogLake(null);
      setMapClickLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setFocusedAnalogLake(null);
    setMapClickLoading(true);

    const matchingRegion = regions.find((region) => region.region_id === focusedAnalogRegionId) ?? null;

    if (!matchingRegion) {
      setFocusedAnalogLake(null);
      setMapClickLoading(false);
      return () => {
        cancelled = true;
      };
    }

    getLakeGeometry(matchingRegion.lake_id)
      .then((lake) => {
        if (cancelled) return;
        setFocusedAnalogLake(lake);
      })
      .catch(() => {
        if (!cancelled) setFocusedAnalogLake(null);
      })
      .finally(() => {
        if (!cancelled) setMapClickLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [focusedAnalogRegionId, focusedAnalogFocusRevision, regions, setMapClickLoading]);

  // ── Shared handler: load geometry and highlight lake ─────────────────────
  const loadLakeGeometry = useCallback(async (lakeId: number) => {
    const reqId = ++lakeRequestId.current;
    setSelectedLake(null);
    setActiveLakeId(lakeId);
    setFocusedAnalogRegionId(null);
    setLakeSearchError(null);
    setLakeLoading(true);
    try {
      const geo = await getLakeGeometry(lakeId);
      if (lakeRequestId.current === reqId) {
        setSelectedLake(geo);
        setSelectedLakeQuery(geo.display_name);
        setCommittedLakeQuery(geo.display_name);
        if (geo.region_id && geo.center_lat !== null && geo.center_lon !== null) {
          selectRegion(geo.region_id, geo.center_lat, geo.center_lon);
        } else {
          setLakeSearchError('No similarity embedding is available for this lake yet.');
        }
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

  const clearLakeSelection = useCallback(() => {
    lakeRequestId.current += 1;
    setSelectedLake(null);
    setActiveLakeId(null);
    setFocusedAnalogRegionId(null);
    setSelectedLakeQuery('');
    setCommittedLakeQuery(null);
    setLakeSearchError(null);
    setLakeLoading(false);
    clearRegion();
  }, [clearRegion]);

  const handleRegionSelect = useCallback(
    (region: LakeRegionResponse) => {
      setSelectedLake(null);
      setFocusedAnalogRegionId(null);
      selectRegion(region.region_id, region.center_lat, region.center_lon);
      setActiveTab('overview');
    },
    [selectRegion, setActiveTab, setSelectedLake],
  );

  const handleAnalogClick = useCallback(
    (analog: AnalogResult) => {
      setFocusedAnalogRegionId(analog.region_id);
      setActiveTab('analogs');
    },
    [setActiveTab, setFocusedAnalogRegionId],
  );

  /** Called when user picks a lake from the search bar */
  const handleLakeSearchSelect = useCallback((lake: LakeSearchResult) => {
    setSelectedLakeQuery(lake.display_name);
    setCommittedLakeQuery(lake.display_name);
    void loadLakeGeometry(lake.lake_id);
  }, [loadLakeGeometry]);

  const handleLakeSearchChange = useCallback((query: string) => {
    setSelectedLakeQuery(query);
    setCommittedLakeQuery(null);
    if (query.trim().length === 0) {
      setSelectedLake(null);
      setActiveLakeId(null);
      setFocusedAnalogRegionId(null);
      setLakeSearchError(null);
      setLakeLoading(false);
      clearRegion();
    }
  }, [clearRegion, setFocusedAnalogRegionId]);

  /** Called when user clicks a lake marker pin */
  const handleMarkerClick = useCallback((lake: LakeMarker) => {
    setSelectedLakeQuery(lake.display_name);
    setCommittedLakeQuery(lake.display_name);
    void loadLakeGeometry(lake.lake_id);
  }, [loadLakeGeometry]);

  const isLoadingGeometry = lakeLoading || mapClickLoading;
  const isLoadingInitialMapData = isLoadingRegions || isLoadingLakeMarkers;

  return (
    <div className="relative h-full w-full">
      {/* Search bar */}
      <LakeSearch
        query={selectedLakeQuery}
        committedQuery={committedLakeQuery}
        onQueryChange={handleLakeSearchChange}
        onSelect={handleLakeSearchSelect}
        onClear={clearLakeSelection}
      />

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

        <MapTabEffects activeTab={activeTab} analogs={similarityData?.analogs ?? []} />

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
        {selectedLake && (
          <SelectedLakePolygon lake={selectedLake} focusRevision={selectedLakeFocusRevision} />
        )}

        {/* Focused similar-lake boundary */}
        {focusedAnalogLake && (
          <FocusedAnalogPolygon
            lake={focusedAnalogLake}
            analogs={similarityData?.analogs ?? []}
            onZoomOut={() => setFocusedAnalogRegionId(null)}
          />
        )}

        {/* Blue dot for selected sub-region */}
        {selectedRegionLat !== null && selectedRegionLon !== null && (
          <SelectedRegionMarker lat={selectedRegionLat} lon={selectedRegionLon} />
        )}

        {/* Analog markers */}
        {similarityData && similarityData.analogs.length > 0 && (
          <AnalogLayer
            analogs={similarityData.analogs}
            highlightedId={highlightedAnalogId}
            activeId={focusedAnalogRegionId}
            onHover={setHighlightedAnalogId}
            onClick={handleAnalogClick}
          />
        )}

      </MapContainer>

      {isLoadingInitialMapData && (
        <div className="absolute inset-0 z-[1100] flex items-center justify-center bg-surface-900/45 backdrop-blur-[2px]" role="status" aria-live="polite">
          <div className="flex items-center gap-3 rounded-xl border border-slate-700/60 bg-surface-800/95 px-5 py-4 shadow-2xl">
            <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
            <span className="text-sm font-medium text-slate-200">Loading map data…</span>
          </div>
        </div>
      )}

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
            <span
              className={clsx(
                'text-[10px]',
                activeTab === 'analogs'
                  ? 'text-slate-500'
                  : showLakeMarkers
                  ? 'text-cyan-300'
                  : 'text-slate-400',
              )}
            >
              Show Lakes
            </span>
            {showLakeMarkers && activeTab !== 'analogs' && (
              <span className="h-2 w-2 flex-shrink-0 rounded-full border border-cyan-400 bg-cyan-500/60" />
            )}
          </label>

          {/* Selected lake dot */}
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 flex-shrink-0 rounded-full border border-yellow-400 bg-yellow-400/60" />
            <span className="text-[10px] text-slate-400">Selected Lake</span>
          </div>

          {/* Similar Lakes */}
          {regions.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 flex-shrink-0 rounded-full border border-green-400 bg-green-500/60" />
              <span className="text-[10px] text-slate-400">Similar Lakes</span>
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
