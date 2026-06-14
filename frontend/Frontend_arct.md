# EcoTwin — Frontend Architecture

A detailed technical reference for the frontend codebase: structure, design patterns, component responsibilities, data flow, and state management.

---

## Table of Contents

- [Design Principles](#design-principles)
- [High-Level Architecture](#high-level-architecture)
- [Layer Overview](#layer-overview)
- [Folder & File Reference](#folder--file-reference)
  - [Root config files](#root-config-files)
  - [src/types/](#srctypes)
  - [src/api/](#srcapi)
  - [src/store/](#srcstore)
  - [src/hooks/](#srchooks)
  - [src/components/common/](#srccomponentscommon)
  - [src/components/Layout/](#srccomponentslayout)
  - [src/components/Map/](#srccomponentsmap)
  - [src/components/RegionPanel/](#srccomponentsregionpanel)
  - [src/components/AnalogPanel/](#srccomponentsanalogpanel)
  - [src/components/TemporalChart/](#srccomponentstemporalchart)
  - [src/components/ForecastPanel/](#srccomponentsforecastpanel)
  - [src/components/ReportPanel/](#srccomponentsreportpanel)
  - [src/pages/](#srcpages)
- [Data Flow — Request Lifecycle](#data-flow--request-lifecycle)
- [State Architecture](#state-architecture)
- [Map Layer Design](#map-layer-design)
- [Sidebar Tab System](#sidebar-tab-system)
- [Report Generation Flow](#report-generation-flow)
- [Styling System](#styling-system)
- [TODO (Manual)](#todo-manual)

---

## Design Principles

1. **Unidirectional data flow** — map click → Zustand store → TanStack Query → component render. No prop drilling beyond 1 level.
2. **Co-location** — each feature panel owns its own data hook, layout, and styles in a single folder. Adding a new panel means adding one folder.
3. **Optimistic UI** — cache-first reads via TanStack Query with 5-minute stale time; Redis on the server provides a 24-hour backing cache.
4. **Progressive disclosure** — the sidebar tabs are disabled until a region is selected. The map is always available even when the API is slow.
5. **Graceful degradation** — all panels show a skeleton / error state independently. A failure in the Forecast panel does not affect the Temporal panel.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       Browser (SPA)                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                     MapPage                            │  │
│  │                                                        │  │
│  │  ┌─────────────────┐    ┌───────────────────────────┐  │  │
│  │  │   Sidebar        │    │       EcoTwinMap           │  │  │
│  │  │  ┌───────────┐  │    │  ┌─────────────────────┐  │  │  │
│  │  │  │ RegionPanel│  │    │  │  Satellite Basemap   │  │  │  │
│  │  │  │ AnalogPanel│  │    │  │  Selected Region     │  │  │  │
│  │  │  │ Temporal   │  │    │  │  Analog Markers      │  │  │  │
│  │  │  │ Forecast   │  │    │  │  Similarity Legend   │  │  │  │
│  │  │  │ Report     │  │    │  └─────────────────────┘  │  │  │
│  │  │  └───────────┘  │    └───────────────────────────┘  │  │
│  │  └─────────────────┘                                    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────┐   ┌─────────────────────┐   ┌────────────┐  │
│  │  Zustand   │   │  TanStack Query     │   │   Axios    │  │
│  │  mapStore  │   │  (region/analogs/   │   │  apiClient │  │
│  │            │   │   temporal/forecast)│   │            │  │
│  └────────────┘   └─────────────────────┘   └────┬───────┘  │
└─────────────────────────────────────────────────┼────────────┘
                                                   │ HTTP
                                        ┌──────────▼──────────┐
                                        │  FastAPI Backend     │
                                        │  /api/v1/...         │
                                        └──────────────────────┘
```

---

## Layer Overview

| Layer | Location | Responsibility |
|---|---|---|
| **Pages** | `src/pages/` | Top-level layout composition |
| **Components** | `src/components/` | Feature panels + UI primitives |
| **Hooks** | `src/hooks/` | Data fetching, caching, mutations |
| **Store** | `src/store/` | Global ephemeral UI state |
| **API** | `src/api/` | HTTP calls, request/response shaping |
| **Types** | `src/types/` | TypeScript contracts (mirrors backend schemas) |

---

## Folder & File Reference

### Root config files

| File | Purpose |
|---|---|
| `index.html` | Single HTML shell. Loads Inter font from Google Fonts, sets `<title>`. |
| `package.json` | All dependencies with pinned semver. Scripts: `dev`, `build`, `preview`, `lint`, `type-check`. |
| `tsconfig.json` | Strict TypeScript, `@/*` path alias mapped to `src/`. |
| `vite.config.ts` | React plugin, `@/` alias, dev server proxy (`/api → localhost:8000`), manual chunk splitting for Leaflet/Recharts/React. |
| `tailwind.config.ts` | Dark mode (`class`), extended `primary` colour (emerald scale), `surface` neutral scale, custom animations (`fade-in`, `slide-in`). |
| `postcss.config.js` | Tailwind + Autoprefixer pipeline. |
| `.env.example` | Documents all `VITE_*` variables. |

---

### `src/types/`

| File | Exports |
|---|---|
| `index.ts` | All TypeScript interfaces that mirror the backend's Pydantic schemas: `Region`, `RegionFeature`, `RegionSummary`, `AnalogResult`, `SimilarityResponse`, `YearlyIndicator`, `TemporalData`, `ForecastHorizon`, `ForecastData`, `Report`, `ReportRequest`, `SidebarTab`, `TrendDirection`. |

Types are decoupled from components. If the backend schema changes, only this file and the affected API module need updating.

---

### `src/api/`

All HTTP communication. Each module exports pure async functions that return typed data or throw `Error`.

| File | Functions | Notes |
|---|---|---|
| `client.ts` | — | Axios instance with `baseURL=/api/v1`, 30s timeout, JWT interceptor, error normaliser (unwraps `detail` from `ApiError`). |
| `regions.ts` | `getRegion(id)`, `queryRegionByCoords(lat, lon)` | `queryRegionByCoords` sends `POST /regions/query` and returns the nearest grid cell. |
| `similarity.ts` | `getAnalogs(regionId, topK, year?)` | `GET /similarity/{id}?top_k=&year=` |
| `temporal.ts` | `getTemporalProfile(regionId)` | `GET /temporal/{id}` |
| `forecast.ts` | `getForecast(regionId)` | `GET /forecast/{id}` |
| `reports.ts` | `createReport(request)`, `getReport(reportId)` | `POST /report`, `GET /report/{id}` |

---

### `src/store/`

| File | Store | Key State |
|---|---|---|
| `mapStore.ts` | `useMapStore` (Zustand) | `selectedRegionId`, `selectedRegionLat/Lon`, `activeTab`, `topK`, `highlightedAnalogId`, `mapClickLoading`, `isSidebarCollapsed` |

**Actions:**
- `selectRegion(id, lat, lon)` — sets region + resets tab to `overview`
- `clearRegion()` — full reset
- `setActiveTab(tab)` — switches sidebar panel
- `setTopK(k)` — triggers analog refetch
- `setHighlightedAnalogId(id)` — cross-links sidebar hover ↔ map circle highlight
- `toggleSidebar()` — collapse/expand sidebar

The store uses the `devtools` middleware (Zustand) for Redux DevTools visibility in development.

---

### `src/hooks/`

All hooks are thin wrappers around TanStack Query. They are enabled only when `regionId !== null`.

| Hook | Query key | Backend endpoint |
|---|---|---|
| `useRegion(regionId)` | `['region', regionId]` | `GET /regions/{id}` |
| `useSimilarity(regionId, topK, year?)` | `['similarity', regionId, topK, year]` | `GET /similarity/{id}?top_k=&year=` |
| `useTemporal(regionId)` | `['temporal', regionId]` | `GET /temporal/{id}` |
| `useForecast(regionId)` | `['forecast', regionId]` | `GET /forecast/{id}` |
| `useReport()` | mutation (no query key) | `POST /report`, `GET /report/{id}` |

**`useReport` design:**
- Uses `useMutation` for the initial `POST`
- Starts a `setInterval` poll every 3 seconds after the job is created
- Stops polling when `status === 'completed'` or `status === 'failed'`
- Max poll attempts = 40 (2 minutes timeout) to prevent runaway loops
- `reset()` clears state and stops polling

---

### `src/components/common/`

Reusable UI primitives with no business logic or data fetching.

| Component | Props | Purpose |
|---|---|---|
| `LoadingSpinner` | `size`, `label`, `className` | Spinning border animation. Sizes: `sm/md/lg`. |
| `ErrorMessage` | `message`, `onRetry`, `compact`, `className` | Full card or inline compact error. Shows retry button when `onRetry` is provided. |
| `Card` | `title`, `subtitle`, `action`, `noPadding`, `className` | Dark surface card with optional header. |
| `Badge` | `label`, `variant`, `dot`, `className` | Coloured pill label. Variants: `default/success/warning/danger/info/increasing/declining/stable`. |

`Badge` also exports `trendToBadgeVariant(trend)` — maps a `TrendDirection` string to the correct badge variant.

---

### `src/components/Layout/`

| Component | Purpose |
|---|---|
| `Navbar` | Fixed top bar. Shows EcoTwin logo, sidebar toggle, selected region coordinates + ecosystem type (from `useRegion`), and a live "region active / click map" status indicator. |

---

### `src/components/Map/`

The most complex component. Entirely self-contained using React-Leaflet.

| Internal Layer | Purpose |
|---|---|
| `MapClickHandler` | `useMapEvents` hook; on click calls `queryRegionByCoords` and dispatches `selectRegion` to the store. Shows a pulsing `CircleMarker` at the click point while loading. |
| `SelectedRegionLayer` | Dashed `Rectangle` outline + centre `CircleMarker` with a "Selected" tooltip for the active region. |
| `AnalogLayer` | `CircleMarker` per analog result. Colour-coded by similarity score (emerald → red). Supports hover highlight (cross-links with `highlightedAnalogId`) and click-to-navigate. Shows a `Popup` with full analog metadata. |
| `EcoTwinMap` (default) | Hosts the `MapContainer` with ESRI World Imagery satellite basemap + ESRI boundary labels overlay. Renders all sub-layers. Includes similarity legend and map-click hint overlay. |

**Similarity colour mapping:**

| Score | Colour |
|---|---|
| ≥ 85% | Emerald `#22c55e` |
| 70–85% | Lime `#84cc16` |
| 55–70% | Yellow `#eab308` |
| 40–55% | Orange `#f97316` |
| < 40% | Red `#ef4444` |

---

### `src/components/RegionPanel/`

| Component | Key internals |
|---|---|
| `RegionPanel` | `useRegion` hook. Shows: region UUID (with copy button), lat/lon, cell area, dominant ecosystem badge. `IndicatorBar` sub-component draws a proportional coloured bar for NDVI/NDWI/NBR mean values. Shows std deviation grid below. Empty state for `!selectedRegionId`. |

---

### `src/components/AnalogPanel/`

| Component | Key internals |
|---|---|
| `AnalogPanel` | `useSimilarity` hook. Top-K selector (5/10/15/20). `SimilarityRing` sub-component draws an SVG arc (cosine distance expressed as arc completion). `AnalogCard` is an interactive button — hover fires `setHighlightedAnalogId`, click fires `selectRegion`. Search latency displayed in header. |

---

### `src/components/TemporalChart/`

| Component | Key internals |
|---|---|
| `TemporalChart` | `useTemporal` hook. Indicator toggle buttons (always ≥ 1 active). Builds `ChartRow[]` by merging NDVI/NDWI/NBR arrays by year. Recharts `LineChart` with `CartesianGrid`, custom dark `Tooltip`. Summary stats grid shows mean ± Δ per visible indicator. |

---

### `src/components/ForecastPanel/`

| Component | Key internals |
|---|---|
| `ForecastPanel` | `useForecast` + `useTemporal` hooks. Indicator selector (NDVI / NDWI / NBR). Recharts `ComposedChart` with: `Area` (confidence band), solid `Line` (historical), dashed `Line` (forecast), `ReferenceLine` at `current_year`. Forecast table (year, value, confidence %). Explanation box. Trend badges with directional icons. |

---

### `src/components/ReportPanel/`

| Component | Key internals |
|---|---|
| `ReportPanel` | `useReport` hook. Toggle switches for include_forecast / include_analogs. Range slider for top_k_analogs (1–20). On submit: shows status card with processing animation. When `completed`: renders a direct `<a download>` link to the PDF URL. When `failed`: shows error. Reset button to generate again. |

---

### `src/pages/`

| File | Purpose |
|---|---|
| `MapPage.tsx` | Top-level layout. Renders `Navbar` + horizontal split: collapsible `Sidebar` (360 px, animated with CSS `transition-all`) + `EcoTwinMap` (fills remaining width). `Sidebar` contains the tab bar and a scrollable content area hosting the active panel. |

**Tab system:**
- Five tabs: Overview / Analogs / Temporal / Forecast / Report
- Tabs requiring a region (`requiresRegion: true`) are visually disabled and non-interactive until `selectedRegionId` is set
- Active tab content renders with a `tab-content-enter` fade-in animation

---

## Data Flow — Request Lifecycle

### Full flow: map click → region summary displayed

```
1. User clicks map
2. MapClickHandler.onClick (React-Leaflet useMapEvents)
3. queryRegionByCoords(lat, lon)  →  POST /api/v1/regions/query
4. Result: { region_id, center_lat, center_lon, distance_km }
5. useMapStore.selectRegion(id, lat, lon)
     → sets selectedRegionId, activeTab = 'overview'
6. RegionPanel re-renders
7. useRegion(selectedRegionId) → TanStack Query
     → cache miss → GET /api/v1/regions/{id}
     → returns RegionSummary
8. RegionPanel renders region data + indicator bars
9. EcoTwinMap reads selectedRegionLat/Lon from store
     → SelectedRegionLayer renders dashed rectangle
10. useSimilarity(selectedRegionId, topK) fires in background
     → GET /api/v1/similarity/{id}?top_k=10
     → AnalogLayer renders color-coded circles on map
```

---

## State Architecture

```
                    Zustand mapStore
                         │
         ┌───────────────┼───────────────┐
         │               │               │
   EcoTwinMap       Sidebar          Navbar
   (reads lat/lon,  (reads tab,      (reads
    highlightId,     regionId)        regionId)
    topK)
         │               │
    AnalogLayer     panel hooks
    (reads          (useRegion,
     highlightId)    useSimilarity,
                     useTemporal,
                     useForecast,
                     useReport)
```

**Why split between Zustand and TanStack Query?**

- **Zustand** handles ephemeral UI state that has no server representation: selected region ID, active tab, which analog is highlighted, sidebar collapsed state. This state needs to be shared across components at different levels of the tree without prop drilling.
- **TanStack Query** handles all server state: it owns the cache, deduplications, stale-time, and background refetch behaviour for API data.

---

## Map Layer Design

```
MapContainer (React-Leaflet)
├── TileLayer — ESRI World Imagery (satellite basemap)
├── TileLayer — ESRI Boundaries + Labels (overlay, 0.7 opacity)
├── ZoomControl (bottom-right)
├── MapClickHandler (invisible event listener)
├── SelectedRegionLayer (Rectangle + CircleMarker)
│     rendered when: selectedRegionLat !== null
└── AnalogLayer (N × CircleMarker + Popup)
      rendered when: similarity data has analogs
```

The map uses `preferCanvas: true` for better performance when many analog markers are rendered simultaneously.

---

## Sidebar Tab System

```
TABS array (MapPage.tsx)
├── { id: 'overview',  requiresRegion: false }  ← always accessible
├── { id: 'analogs',   requiresRegion: true  }
├── { id: 'temporal',  requiresRegion: true  }
├── { id: 'forecast',  requiresRegion: true  }
└── { id: 'report',    requiresRegion: true  }

Tab bar renders each tab button:
  - disabled + dimmed   if requiresRegion && !selectedRegionId
  - active (green line) if id === activeTab
  - hover state         otherwise

Content area: conditional render of active panel component
Tab switch triggers fade-in animation via .tab-content-enter class
```

---

## Report Generation Flow

```
User configures options in ReportPanel
        │
        ▼
handleGenerate() → useReport.generate(request)
        │
        ▼
useMutation → POST /api/v1/report
        │
        ▼
Backend creates Report row (status=PENDING)
Returns immediately with report_id + status=PROCESSING
        │
        ▼
useReport: setReport(data), startPolling(report_id)
        │
setInterval every 3s → GET /api/v1/report/{id}
        │
        ├── status=processing → update UI, continue polling
        ├── status=completed  → stopPolling, show Download button
        └── status=failed     → stopPolling, show error
```

---

## Styling System

The UI uses **TailwindCSS** with a custom dark palette:

| Token | Usage |
|---|---|
| `surface-900` (#0f172a) | Page background |
| `surface-800` (#1e293b) | Cards, sidebar, navbar |
| `surface-700` (#334155) | Hover states, grid lines |
| `primary-400/500/600` (emerald) | Active states, selected region, badges |
| `slate-100–600` | Text hierarchy |
| `red-400`, `amber-400`, `emerald-400` | Semantic status colours |

Global CSS (`index.css`) handles:
- Leaflet popup dark theme override
- Custom 4px scrollbar (`.scrollbar-thin`)
- `.tab-content-enter` fade-in animation
- Map cursor override (`crosshair`)

---

## TODO (Manual)

This section tracks known gaps and planned improvements.
Update manually as items are completed or new ones are identified.

### High Priority

- [ ] **Authentication UI** — Login / register screens with JWT token storage and refresh; currently the Axios client reads a token from `localStorage` but no auth pages exist
- [ ] **Map study area boundary** — Draw the project boundary polygon on the map so users know which area has data coverage
- [ ] **Mobile responsive layout** — Sidebar is fixed 360 px wide; needs a bottom-sheet or full-screen overlay pattern for screens < 768 px
- [ ] **Error boundary** — Wrap each panel in a React ErrorBoundary so a JS runtime error in one panel doesn't crash the whole app
- [ ] **Toast notifications** — Global toast/snackbar system for success/error feedback (e.g. "Region found", "Report submitted")

### Medium Priority

- [ ] **Region comparison mode** — Allow selecting 2 regions and showing side-by-side temporal charts on the same axis
- [ ] **Year selector** — Dropdown to select the observation year for the similarity search (currently defaults to latest)
- [ ] **Map search bar** — Add a geocoder input (nominatim / mapbox) to fly-to a named location rather than manually panning
- [ ] **Export chart as PNG** — Add a download button to each Recharts chart using `html2canvas` or the built-in SVG export
- [ ] **Forecast confidence toggle** — Option to hide/show the confidence band on the forecast chart
- [ ] **Bookmark / share region** — URL parameter (`?region=<uuid>`) that pre-selects a region on load so users can share links

### Low Priority

- [ ] **Dark / Light theme toggle** — The TailwindCSS `dark:` variant is already configured; needs a toggle button and `localStorage` persistence
- [ ] **Keyboard navigation** — Tab through sidebar panels, press `Escape` to clear region, arrow keys on analog cards
- [ ] **Analog map clustering** — At low zoom levels with many analog markers, use Leaflet.markercluster to prevent overlap
- [ ] **Animated map fly-to** — When a region is selected, animate the map to center on the new region using `map.flyTo()`
- [ ] **Storybook** — Isolated component stories for Badge, Card, LoadingSpinner, SimilarityRing, IndicatorBar
- [ ] **Unit tests** — Jest + React Testing Library tests for hooks (`useReport` polling logic) and pure utility functions
- [ ] **i18n** — Internationalisation with `react-i18next` if the platform expands to non-English users
- [ ] **PWA** — Service worker + manifest for offline access to cached region data

### Completed

- [x] Satellite basemap (ESRI World Imagery) with labels overlay
- [x] Map click → nearest region lookup via API
- [x] Selected region dashed rectangle + center marker
- [x] Analog circle markers with cosine-similarity colour coding
- [x] Cross-highlight: sidebar hover ↔ map circle
- [x] Collapsible 360 px sidebar with animated transition
- [x] 5-tab sidebar system with disabled states
- [x] Overview panel — NDVI/NDWI/NBR indicator bars
- [x] Analog panel — similarity rings, ranked cards, Top-K selector
- [x] Temporal panel — multi-indicator line chart with toggle
- [x] Forecast panel — ComposedChart with confidence band + forecast table
- [x] Report panel — options, async generate, polling, PDF download link
- [x] TanStack Query caching (5 min stale, 10 min gc)
- [x] Zustand store with devtools
- [x] TypeScript strict mode throughout
- [x] Tailwind dark palette + custom scrollbar + Leaflet popup override
