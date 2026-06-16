/**
 * IndiaStateLayer — renders India state boundaries from a public GeoJSON CDN.
 *
 * Behaviour:
 *  • Overview mode (activeState = null):
 *      - All states rendered as polygons.
 *      - Grey   = no pipeline data.
 *      - Teal   = state has been synced.
 *      - Click on a synced state → onStateSelect(canonicalName, feature).
 *      - Click on a grey state   → nothing (tooltip guides user to Sync).
 *  • Drill-down mode (activeState = string):
 *      - All states dimmed grey.
 *      - Active state highlighted with a bright sky-blue outline.
 *      - Map auto-fits to that state's bounds.
 *      - GeoJSON clicks disabled (MapClickHandler takes over for region query).
 */

import { useEffect, useRef } from 'react';
import { GeoJSON, useMap } from 'react-leaflet';
import type { Layer, PathOptions, StyleFunction } from 'leaflet';
import type { Feature, GeoJsonObject } from 'geojson';

// ── GeoJSON property name → our canonical INDIA_STATE_CENTROIDS key ──────────
// Source: https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson
// Property: ST_NM
const GEO_TO_CANONICAL: Record<string, string> = {
  'Andaman & Nicobar Island':  'Andaman and Nicobar',
  'Andhra Pradesh':            'Andhra Pradesh',
  'Arunachal Pradesh':         'Arunachal Pradesh',
  'Assam':                     'Assam',
  'Bihar':                     'Bihar',
  'Chandigarh':                'Chandigarh',
  'Chhattisgarh':              'Chhattisgarh',
  'Dadra & Nagar Haveli':      'Dadra and Nagar Haveli',
  'Daman & Diu':               'Daman and Diu',
  'Goa':                       'Goa',
  'Gujarat':                   'Gujarat',
  'Haryana':                   'Haryana',
  'Himachal Pradesh':          'Himachal Pradesh',
  'Jammu & Kashmir':           'Jammu and Kashmir',
  'Jharkhand':                 'Jharkhand',
  'Karnataka':                 'Karnataka',
  'Kerala':                    'Kerala',
  'Lakshadweep':               'Lakshadweep',
  'Madhya Pradesh':            'Madhya Pradesh',
  'Maharashtra':               'Maharashtra',
  'Manipur':                   'Manipur',
  'Meghalaya':                 'Meghalaya',
  'Mizoram':                   'Mizoram',
  'Nagaland':                  'Nagaland',
  'NCT of Delhi':              'Delhi',
  'Odisha':                    'Odisha',
  'Puducherry':                'Puducherry',
  'Punjab':                    'Punjab',
  'Rajasthan':                 'Rajasthan',
  'Sikkim':                    'Sikkim',
  'Tamil Nadu':                'Tamil Nadu',
  'Telangana':                 'Telangana',
  'Tripura':                   'Tripura',
  'Uttar Pradesh':             'Uttar Pradesh',
  'Uttarakhand':               'Uttarakhand',
  'West Bengal':               'West Bengal',
  // Alternate spellings sometimes present in the GeoJSON
  'Uttaranchal':               'Uttarakhand',
  'Orissa':                    'Odisha',
  'Pondicherry':               'Puducherry',
  'Ladakh':                    'Ladakh',
};

// ── Colours ───────────────────────────────────────────────────────────────────
const COLOR_NO_DATA    = '#6b7280';  // slate-500
const COLOR_HAS_DATA   = '#14b8a6';  // teal-500
const COLOR_ACTIVE     = '#38bdf8';  // sky-400
const FILL_NO_DATA     = 0.12;
const FILL_HAS_DATA    = 0.28;
const FILL_ACTIVE      = 0.20;
const WEIGHT_DEFAULT   = 1;
const WEIGHT_ACTIVE    = 2.5;

// ── Props ─────────────────────────────────────────────────────────────────────
interface IndiaStateLayerProps {
  geoData: GeoJsonObject;
  syncedStates: string[];              // canonical state names with data
  activeState: string | null;          // null = overview; string = drill-down
  onStateSelect: (canonical: string, feature: Feature) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function IndiaStateLayer({
  geoData,
  syncedStates,
  activeState,
  onStateSelect,
}: IndiaStateLayerProps) {
  const map = useMap();
  const syncedSet = new Set(syncedStates);
  const geoJsonRef = useRef<L.GeoJSON | null>(null);

  // ── Fit bounds when active state changes ──────────────────────────────────
  useEffect(() => {
    if (!activeState || !geoJsonRef.current) return;

    // Find the layer for the active state and fit bounds
    geoJsonRef.current.eachLayer((layer) => {
      const f = (layer as L.GeoJSON & { feature?: Feature }).feature;
      if (!f?.properties) return;
      const rawName: string = f.properties['ST_NM'] ?? f.properties['NAME_1'] ?? f.properties['name'] ?? '';
      const canonical = GEO_TO_CANONICAL[rawName] ?? rawName;
      if (canonical === activeState) {
        const bounds = (layer as L.Path & { getBounds?: () => L.LatLngBounds }).getBounds?.();
        if (bounds) {
          map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 });
        }
      }
    });
  }, [activeState, map]);

  // ── Style function ────────────────────────────────────────────────────────
  const styleFeature: StyleFunction<GeoJsonProperties> = (feature) => {
    if (!feature?.properties) return {};
    const rawName: string = feature.properties['ST_NM'] ?? feature.properties['NAME_1'] ?? feature.properties['name'] ?? '';
    const canonical = GEO_TO_CANONICAL[rawName] ?? rawName;
    const hasData  = syncedSet.has(canonical);
    const isActive = canonical === activeState;

    if (isActive) {
      return {
        color:       COLOR_ACTIVE,
        weight:      WEIGHT_ACTIVE,
        fillColor:   COLOR_ACTIVE,
        fillOpacity: FILL_ACTIVE,
        opacity:     0.9,
      } satisfies PathOptions;
    }

    if (activeState) {
      // In drill-down mode: all other states are dimmed
      return {
        color:       COLOR_NO_DATA,
        weight:      WEIGHT_DEFAULT,
        fillColor:   COLOR_NO_DATA,
        fillOpacity: 0.06,
        opacity:     0.4,
      } satisfies PathOptions;
    }

    return {
      color:       hasData ? COLOR_HAS_DATA : COLOR_NO_DATA,
      weight:      WEIGHT_DEFAULT,
      fillColor:   hasData ? COLOR_HAS_DATA : COLOR_NO_DATA,
      fillOpacity: hasData ? FILL_HAS_DATA : FILL_NO_DATA,
      opacity:     0.7,
    } satisfies PathOptions;
  };

  // ── Per-feature event binding ─────────────────────────────────────────────
  const onEachFeature = (feature: Feature, layer: Layer) => {
    if (!feature.properties) return;
    const rawName: string =
      feature.properties['ST_NM'] ??
      feature.properties['NAME_1'] ??
      feature.properties['name'] ??
      'Unknown';
    const canonical = GEO_TO_CANONICAL[rawName] ?? rawName;
    const hasData   = syncedSet.has(canonical);

    // Tooltip
    (layer as L.Path).bindTooltip(
      hasData
        ? `<strong>${canonical}</strong><br/><span style="color:#14b8a6">Data available — click to explore</span>`
        : `<strong>${canonical}</strong><br/><span style="color:#6b7280">No data — sync this state first</span>`,
      { sticky: true, className: 'ecotwin-state-tooltip' },
    );

    // Click handler (only active in overview mode)
    layer.on('click', () => {
      if (activeState) return; // drill-down mode: map click handler takes over
      if (!hasData) return;    // grey state: do nothing
      onStateSelect(canonical, feature);
    });

    // Hover highlight (only in overview mode, only for synced states)
    layer.on('mouseover', () => {
      if (activeState || !hasData) return;
      (layer as L.Path).setStyle({
        fillOpacity: 0.45,
        weight: 2,
      });
    });
    layer.on('mouseout', () => {
      if (activeState || !hasData) return;
      (layer as L.Path).setStyle({
        fillOpacity: FILL_HAS_DATA,
        weight: WEIGHT_DEFAULT,
      });
    });
  };

  return (
    <GeoJSON
      // Re-mount the layer whenever synced states or active state changes
      key={`${syncedStates.join(',')}::${activeState ?? 'overview'}`}
      data={geoData}
      style={styleFeature}
      onEachFeature={onEachFeature}
      ref={geoJsonRef}
    />
  );
}

// ── Type helpers ──────────────────────────────────────────────────────────────
// GeoJSON properties are untyped at the library level
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type GeoJsonProperties = Record<string, any> | null;
