# EcoTwin — Frontend

Interactive geospatial ecosystem discovery, similarity search, temporal analysis, and analog forecasting dashboard.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Environment Setup](#environment-setup)
- [Running Locally](#running-locally)
- [Building for Production](#building-for-production)
- [Running with Docker (Full Stack)](#running-with-docker-full-stack)
- [Linting & Type Checking](#linting--type-checking)
- [Key Interactions](#key-interactions)
- [Environment Variables](#environment-variables)

---

## Overview

The EcoTwin frontend is a single-page React application that provides an interactive map-based interface for:

- Clicking any location on a satellite basemap to identify the nearest 5 km × 5 km ecosystem grid cell
- Discovering globally similar ecosystems via vector similarity search
- Visualising NDVI / NDWI / NBR historical trends from 2018 to present
- Generating 5-year analog-based ecosystem forecasts with confidence scoring
- Downloading automated PDF ecosystem reports

---

## Tech Stack

| Category | Library | Version |
|---|---|---|
| Framework | React | 18 |
| Language | TypeScript | 5 |
| Bundler | Vite | 5 |
| Styling | TailwindCSS | 3 |
| Map | React-Leaflet + Leaflet | 4 / 1.9 |
| Charts | Recharts | 2 |
| Data Fetching | TanStack Query (React Query) | 5 |
| Global State | Zustand | 5 |
| HTTP Client | Axios | 1 |
| Icons | Lucide React | latest |

---

## Prerequisites

| Tool | Minimum Version |
|---|---|
| Node.js | 20 LTS |
| npm | 10 |

> The backend API must be running at `http://localhost:8000` (or the URL set in `VITE_API_BASE_URL`).  
> See [backend/README.md](../backend/README.md) for backend setup instructions.

---

## Project Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── .env.example
└── src/
    ├── main.tsx              ← App bootstrap
    ├── App.tsx               ← Root component
    ├── index.css             ← Global styles + Leaflet overrides
    ├── types/                ← TypeScript interfaces
    ├── api/                  ← Axios API modules
    ├── store/                ← Zustand global state
    ├── hooks/                ← TanStack Query hooks
    ├── components/
    │   ├── common/           ← Reusable UI primitives
    │   ├── Layout/           ← Navbar
    │   ├── Map/              ← Leaflet map
    │   ├── RegionPanel/      ← Ecosystem overview
    │   ├── AnalogPanel/      ← Analog similarity results
    │   ├── TemporalChart/    ← Historical time-series charts
    │   ├── ForecastPanel/    ← 5-year forecast charts
    │   └── ReportPanel/      ← PDF report generation
    └── pages/
        └── MapPage.tsx       ← Main layout (sidebar + map)
```

---

## Environment Setup

### 1. Copy the environment file

```bash
cd frontend
cp .env.example .env
```

### 2. Edit `.env` if needed

```env
# Point to your backend API
VITE_API_BASE_URL=http://localhost:8000

# Default map centre (change to your study area)
VITE_MAP_DEFAULT_LAT=20.5937
VITE_MAP_DEFAULT_LNG=78.9629
VITE_MAP_DEFAULT_ZOOM=5
```

---

## Running Locally

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Start the development server

```bash
npm run dev
```

The app opens at **http://localhost:5173**

The Vite dev server automatically proxies `/api/*` requests to the backend at `http://localhost:8000`, so there are no CORS issues during development.

### 3. Check TypeScript types (optional)

```bash
npm run type-check
```

---

## Building for Production

```bash
npm run build
```

Output goes to `dist/`. The build is code-split into vendor chunks for better caching:

| Chunk | Contents |
|---|---|
| `vendor` | React + ReactDOM |
| `leaflet` | Leaflet + React-Leaflet |
| `charts` | Recharts |
| `query` | TanStack Query |

### Preview the production build locally

```bash
npm run preview
```

---

## Running with Docker (Full Stack)

The frontend is served via Nginx inside the Docker Compose stack.  
From the `backend/` folder:

```bash
# Build and start the full stack
docker compose up --build

# The frontend is served at http://localhost (port 80 via Nginx)
# The API is available at http://localhost:8000
```

---

## Linting & Type Checking

```bash
# Run ESLint
npm run lint

# Auto-fix lint issues
npm run lint:fix

# TypeScript type check (no emit)
npm run type-check
```

---

## Key Interactions

| Action | Result |
|---|---|
| Click on map | Nearest 5 km × 5 km region is identified and highlighted |
| Overview tab | Region ID, coordinates, NDVI / NDWI / NBR bars for latest year |
| Analogs tab | Top-K similar ecosystem regions shown as scored cards + map markers |
| Hover analog card | Corresponding map marker highlights |
| Click analog card | Navigates to that region |
| Temporal tab | Multi-year line charts with toggle per indicator |
| Forecast tab | 5-year projected trajectory with confidence band |
| Report tab | Configure and generate downloadable PDF report |
| Collapse sidebar | Full-screen map view |
| Clear region | Resets all panels and map markers |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |
| `VITE_MAP_DEFAULT_LAT` | `20.5937` | Initial map centre latitude |
| `VITE_MAP_DEFAULT_LNG` | `78.9629` | Initial map centre longitude |
| `VITE_MAP_DEFAULT_ZOOM` | `5` | Initial map zoom level |

---

## Authors

Ankit Kumar | Peeyush Prashant | Vikash Kumar
