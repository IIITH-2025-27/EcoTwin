# EcoTwin Frontend — Features

A complete inventory of implemented features and planned additions, organised by domain area.

---

## Table of Contents

- [Implemented Features](#implemented-features)
  - [Map & Navigation](#map--navigation)
  - [Region Discovery](#region-discovery)
  - [Ecosystem Overview](#ecosystem-overview)
  - [Analog Similarity Search](#analog-similarity-search)
  - [Temporal Analysis](#temporal-analysis)
  - [Analog-Based Forecasting](#analog-based-forecasting)
  - [Report Generation](#report-generation)
  - [UI & UX](#ui--ux)
  - [Technical Infrastructure](#technical-infrastructure)
- [Feature TODOs](#feature-todos)
  - [High Priority](#high-priority)
  - [Medium Priority](#medium-priority)
  - [Low Priority](#low-priority)

---

## Implemented Features

### Map & Navigation

| # | Feature | Details |
|---|---|---|
| M-01 | **Satellite basemap** | ESRI World Imagery tile layer for true-colour satellite view |
| M-02 | **Labels overlay** | ESRI World Boundaries & Places semi-transparent overlay on top of satellite |
| M-03 | **Click to discover** | Clicking anywhere on the map fires `POST /regions/query` to find the nearest 5 km × 5 km grid cell |
| M-04 | **Click loading indicator** | Pulsing dot at click location + top banner while API resolves the nearest region |
| M-05 | **Selected region highlight** | Dashed green `Rectangle` outline around the active grid cell with a `CircleMarker` centre dot |
| M-06 | **"Selected" tooltip** | Persistent tooltip pinned above the selected region centre marker |
| M-07 | **Click hint banner** | "Click anywhere to discover an ecosystem" overlay shown when no region is selected |
| M-08 | **Zoom control** | Custom-positioned zoom control (bottom-right) |
| M-09 | **Canvas renderer** | `preferCanvas: true` for performant rendering of many analog markers |
| M-10 | **Cross-hair cursor** | Map cursor set to crosshair to communicate clickability |

---

### Region Discovery

| # | Feature | Details |
|---|---|---|
| R-01 | **Nearest region lookup** | Haversine-based nearest 5 km cell identified server-side within 100 ms |
| R-02 | **Distance feedback** | API returns `distance_km` showing how far the clicked point was from the cell centre |
| R-03 | **Region UUID display** | Full UUID shown with a one-click copy button in the Overview panel |
| R-04 | **Coordinates display** | `center_lat`, `center_lon` shown to 5 decimal places |
| R-05 | **Cell area display** | Grid cell area (25 km² default) shown in the Overview panel |
| R-06 | **Clear region** | "Clear" button in sidebar header resets all panels, markers, and charts |

---

### Ecosystem Overview

| # | Feature | Details |
|---|---|---|
| O-01 | **NDVI indicator bar** | Mean NDVI visualised as a proportional emerald progress bar |
| O-02 | **NDWI indicator bar** | Mean NDWI visualised as a proportional blue progress bar |
| O-03 | **NBR indicator bar** | Mean NBR visualised as a proportional orange progress bar |
| O-04 | **Indicator values** | Exact mean value displayed in monospace alongside each bar |
| O-05 | **Std deviation grid** | σ values for NDVI, NDWI, NBR shown in a 3-column grid below the bars |
| O-06 | **Observation year** | Year of the latest feature record shown next to indicators |
| O-07 | **Dominant ecosystem badge** | Ecosystem classification shown as a coloured pill badge |
| O-08 | **Loading skeleton** | Spinner + "Loading region data…" shown while API request is in-flight |
| O-09 | **Error state** | Error card with message and Retry button on API failure |
| O-10 | **Empty state** | "No indicator data" message when features are absent for the region |

---

### Analog Similarity Search

| # | Feature | Details |
|---|---|---|
| A-01 | **Top-K search** | Retrieves top-K most similar ecosystems via pgvector cosine similarity |
| A-02 | **Top-K selector** | Dropdown to choose K ∈ {5, 10, 15, 20} — triggers automatic refetch |
| A-03 | **Similarity ring** | SVG arc ring per analog showing exact cosine similarity % |
| A-04 | **Colour-coded score** | Ring colour encodes similarity range: emerald (≥85%) → red (<40%) |
| A-05 | **Ranked analog cards** | Analogs displayed as interactive cards ordered by similarity score |
| A-06 | **Analog card details** | Each card shows: lat/lon, observation year, dominant ecosystem |
| A-07 | **UUID preview** | Truncated UUID on each card for identification |
| A-08 | **Sidebar ↔ map highlight** | Hovering an analog card highlights the corresponding map circle (and vice versa) |
| A-09 | **Click to navigate** | Clicking an analog card selects it as the new active region |
| A-10 | **Analog map markers** | All K analogs rendered as `CircleMarker` on the map with the same colour scheme |
| A-11 | **Analog popups** | Clicking a map marker opens a dark popup with full analog metadata |
| A-12 | **Search latency display** | Server-reported search latency (ms) shown in panel header |
| A-13 | **Similarity legend** | Fixed bottom-right map overlay explaining the 5-tier colour scale |
| A-14 | **Year display** | Analog match year shown on card and popup |
| A-15 | **Empty state** | "No analogs found" message when search returns zero results |

---

### Temporal Analysis

| # | Feature | Details |
|---|---|---|
| T-01 | **Multi-year line chart** | Annual NDVI, NDWI, NBR values plotted on a single `LineChart` (2018–present) |
| T-02 | **Indicator toggles** | Pill toggle buttons to show/hide each indicator; at least one always remains visible |
| T-03 | **Active indicator styling** | Active toggle button filled with the indicator colour |
| T-04 | **Domain fixed** | Y-axis domain fixed at [−1, 1] matching the valid range of normalised indices |
| T-05 | **Custom dark tooltip** | Hover tooltip styled to match the dark UI theme |
| T-06 | **Connected null lines** | `connectNulls` ensures lines are drawn even when some years have missing data |
| T-07 | **Summary stats grid** | Below the chart: mean value and Δ (last − first) per visible indicator |
| T-08 | **Delta colouring** | Positive Δ shown in emerald, negative in red, zero in slate |
| T-09 | **Year range label** | Chart subtitle shows "YYYY – YYYY" span from actual data |
| T-10 | **Loading / error states** | Spinner and error card shown during data fetch |

---

### Analog-Based Forecasting

| # | Feature | Details |
|---|---|---|
| F-01 | **5-year forecast horizons** | Predicted NDVI, NDWI, NBR values for the next 5 years |
| F-02 | **Historical + forecast chart** | `ComposedChart` combining solid historical line + dashed forecast line |
| F-03 | **Confidence band** | Shaded `Area` around the forecast line representing ±uncertainty |
| F-04 | **"Now" reference line** | Vertical `ReferenceLine` at `current_year` separating history from forecast |
| F-05 | **Per-year confidence** | Confidence score (0–1) per horizon, decaying with distance from current year |
| F-06 | **Forecast table** | Tabular view of year, predicted value, and confidence % |
| F-07 | **Confidence colouring** | Table confidence cell: emerald (≥70%), amber (50–70%), red (<50%) |
| F-08 | **Analog match display** | Best analog UUID and matched historical year shown in a card |
| F-09 | **Overall confidence bar** | Animated coloured progress bar for overall forecast confidence |
| F-10 | **Trend badges** | Vegetation / Water / Burn severity directional badges (Increasing / Stable / Declining) |
| F-11 | **Trend icons** | `TrendingUp`, `TrendingDown`, `Minus` Lucide icons alongside trend badges |
| F-12 | **Indicator selector** | Switch between NDVI / NDWI / NBR charts with one click |
| F-13 | **Explanation text** | Human-readable analog reasoning text in a blue info box |
| F-14 | **Fallback forecast** | Graceful degradation when no analog is found — extrapolates from own history |

---

### Report Generation

| # | Feature | Details |
|---|---|---|
| P-01 | **Include Forecast toggle** | Toggle whether to include the 5-year forecast section in the PDF |
| P-02 | **Include Analogs toggle** | Toggle whether to include the analog ecosystem section in the PDF |
| P-03 | **Analog count slider** | Range slider (1–20) to set how many analogs appear in the report |
| P-04 | **Async generation** | Report is submitted as a background job; UI returns immediately |
| P-05 | **Status polling** | Frontend polls `GET /report/{id}` every 3 seconds until complete or failed |
| P-06 | **Processing animation** | Three animated steps shown while report is generating |
| P-07 | **PDF download link** | Direct `<a download>` link to the generated PDF file once complete |
| P-08 | **Status indicators** | Clock (pending), spinner (processing), checkmark (completed), X (failed) with colour coding |
| P-09 | **Poll timeout** | Auto-stops polling after 2 minutes and shows timeout error |
| P-10 | **Reset button** | "Generate a new report" resets the entire report flow |
| P-11 | **Error display** | Backend error message shown when generation fails |

---

### UI & UX

| # | Feature | Details |
|---|---|---|
| U-01 | **Dark theme** | Full dark colour palette using Tailwind's `dark:` class mode |
| U-02 | **Collapsible sidebar** | Navbar toggle collapses sidebar to 0 width with CSS transition for full-screen map |
| U-03 | **5-tab sidebar** | Overview / Analogs / Temporal / Forecast / Report tabs |
| U-04 | **Disabled tab states** | Tabs requiring a region are visually greyed out and non-interactive until selection |
| U-05 | **Tab fade animation** | Panel content fades in with a subtle upward translate on tab switch |
| U-06 | **Navbar region summary** | Coordinates and ecosystem type displayed in the navbar while a region is active |
| U-07 | **Custom scrollbar** | 4 px thin scrollbar with dark styling on all scrollable panels |
| U-08 | **Loading spinners** | Consistent `LoadingSpinner` with size variants across all async states |
| U-09 | **Error messages** | `ErrorMessage` with optional retry button in all panels |
| U-10 | **Badge system** | Reusable `Badge` component with 8 semantic variants |
| U-11 | **Card system** | Consistent `Card` component with optional title / subtitle / action slot |
| U-12 | **Responsive Navbar** | Region details hidden on narrow viewports via `hidden sm:flex` |

---

### Technical Infrastructure

| # | Feature | Details |
|---|---|---|
| I-01 | **TanStack Query caching** | 5-minute stale time, 10-minute gc time; server-side Redis ensures freshness |
| I-02 | **Zustand devtools** | Redux DevTools integration for inspecting store state in development |
| I-03 | **Axios interceptors** | JWT token injection + error message normalisation at the HTTP layer |
| I-04 | **Vite proxy** | Dev-server `/api` proxy to backend — no CORS configuration needed in development |
| I-05 | **Code splitting** | Vendor / Leaflet / Recharts / Query manual chunks for optimal caching |
| I-06 | **TypeScript strict mode** | Full strict TypeScript across all source files |
| I-07 | **Leaflet icon fix** | Default marker icon URLs patched for Vite's asset pipeline |
| I-08 | **Path aliases** | `@/` alias maps to `src/` across all imports |
| I-09 | **Environment variables** | All configurable values exposed via `VITE_*` env variables |
| I-10 | **React Query DevTools** | Mounted in dev mode only (`import.meta.env.DEV`) |

---

## Feature TODOs

### High Priority

- [ ] **Authentication screens** — Login / register pages; Axios interceptor already reads JWT from `localStorage` but no auth flow exists
- [ ] **Study area boundary overlay** — Draw the project boundary on the map so users know the coverage area
- [ ] **Mobile responsive sidebar** — Bottom-sheet drawer or full-screen overlay for screens narrower than 768 px
- [ ] **React Error Boundary** — Wrap each panel so a runtime JS crash in one panel doesn't take down the whole page
- [ ] **Toast / snackbar system** — Global feedback for async actions (report submitted, region cleared, copy success)
- [ ] **Accessibility audit** — Keyboard navigation for tab bar, ARIA labels on interactive map elements, focus management on region selection

### Medium Priority

- [ ] **URL-based region sharing** — Persist `?region=<uuid>` in the URL so users can share a direct link to a region
- [ ] **Region comparison mode** — Side-by-side temporal charts for two selected regions on the same Y-axis
- [ ] **Observation year selector** — Dropdown in the Analogs tab to select which year's embedding to search against
- [ ] **Map geocoder** — Search bar to fly to a named place (using Nominatim or Mapbox Geocoding) rather than manually panning
- [ ] **Export chart as PNG** — "Download chart" button on Temporal and Forecast panels
- [ ] **Forecast confidence toggle** — Show/hide the confidence band on the forecast chart
- [ ] **Analog count on map legend** — Show how many analogs are currently rendered in the map legend
- [ ] **Region metadata table** — Paginated `GET /regions` endpoint + table view to browse all indexed regions

### Low Priority

- [ ] **Dark / Light theme toggle** — Tailwind dark variant already configured; needs toggle button + `localStorage` persistence
- [ ] **Animated map fly-to** — Use `map.flyTo()` to smoothly animate to a newly selected region
- [ ] **Marker clustering** — Use `react-leaflet-cluster` to cluster analog markers at low zoom levels
- [ ] **Offline / PWA support** — Service worker + app manifest for offline access to cached region data
- [ ] **Storybook component library** — Isolated stories for Badge, Card, SimilarityRing, IndicatorBar, LoadingSpinner
- [ ] **Unit tests** — React Testing Library tests for `useReport` polling logic and `TemporalChart` data transformation
- [ ] **i18n support** — `react-i18next` for multi-language UI if the platform expands globally
- [ ] **Print-friendly PDF export** — CSS `@media print` or Puppeteer-based screenshot of the forecast chart
- [ ] **Heatmap layer** — Optional NDVI / NDWI raster heatmap overlay on the Leaflet map from pre-computed GeoTIFF tiles
- [ ] **Region search by ID** — Text input to jump directly to a region UUID without clicking the map
