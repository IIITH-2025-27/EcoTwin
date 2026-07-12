# EcoTwin — Backend API

Geospatial Ecosystem Discovery, Similarity Search & Analog Forecasting Platform.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Environment Setup](#environment-setup)
- [Running Locally (Without Docker)](#running-locally-without-docker)
- [Running With Docker](#running-with-docker)
- [Database Migrations](#database-migrations)
- [ML Pipeline & Data Sync](#ml-pipeline--data-sync)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
- [Useful Scripts](#useful-scripts)

---

## Overview

The EcoTwin backend is a high-performance async REST API built with **FastAPI**.  
It powers:

- **Ecosystem region lookup** — nearest 5 km × 5 km grid cell for any lat/lon
- **Analog similarity search** — cosine similarity over 768-dim Prithvi embeddings via `pgvector`
- **Temporal profiles** — year-by-year NDVI / NDWI / NBR trends (2017 – present)
- **Analog-based forecasting** — 5-year outlook derived from historical twin trajectories
- **Automated PDF reports** — generated directly by the API
- **ML data pipeline** — GEE Sentinel-2 ingestion → Prithvi-100M embeddings → ecosystem classification
- **Data sync** — per-state ingestion control via a dedicated sync API

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn / Gunicorn |
| Database | PostgreSQL 16 + PostGIS + pgvector |
| ORM / Migrations | SQLAlchemy 2 (async) + Alembic |
| Cache / Broker | Redis 7 |
| ML Embeddings | PyTorch (CPU) + Prithvi-100M (IBM/NASA) |
| Remote Sensing | Google Earth Engine (Sentinel-2 SR) |
| Ecosystem Classification | Rule-based + optional scikit-learn probe |
| PDF Reports | ReportLab |
| Containerisation | Docker + Docker Compose |

---

## Prerequisites

| Tool | Minimum Version | Install |
|---|---|---|
| Python | 3.12 | [python.org](https://www.python.org/downloads/) |
| PostgreSQL | 16 with PostGIS & pgvector | via Docker (recommended) |
| Redis | 7 | via Docker (recommended) |
| Docker | 24 | [Docker_help.md](./Docker_help.md) |
| Docker Compose | v2 | bundled with Docker Desktop |
| GEE account | — | [earthengine.google.com](https://earthengine.google.com) |

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                 ← FastAPI application factory
│   ├── core/                   ← Config, security, logging, exceptions, DI
│   ├── db/                     ← SQLAlchemy engine & session
│   ├── models/                 ← ORM models (Region, RegionFeature, …)
│   ├── schemas/                ← Pydantic request / response schemas
│   ├── repositories/           ← Data access layer
│   ├── services/               ← Business logic (region, sync, report, …)
│   ├── api/v1/endpoints/       ← Route handlers
│   ├── cache/                  ← Redis client
│   ├── ML_pipeline/            ← GEE ingest, Prithvi inference, classifier
│   │   ├── constants.py        ← All tuneable values (single source of truth)
│   │   ├── gee_ingest.py       ← Phase 1: Sentinel-2 composite → NDVI/NDWI/NBR
│   │   ├── prithvi_inference.py← Phase 2: band array → 768-dim embedding
│   │   ├── _prithvi_model.py   ← PrithviEncoder architecture stub
│   │   ├── classifier.py       ← Phase 3: ecosystem label + confidence
│   │   └── pipeline.py         ← Processing stages (P1 → P2 → P3)
│   └── utils/                  ← Geo utilities
├── alembic/                    ← DB migration scripts
├── tests/                      ← Unit + integration tests
├── scripts/                    ← Init SQL for Docker
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── .env.example
```

---

## Environment Setup

### 1. Copy the environment file

```bash
cp .env.example .env
```

### 2. Edit `.env` — minimum required keys

```env
# ── Database ───────────────────────────────────────────────────────────────
POSTGRES_PASSWORD=your_secure_password

# ── App ────────────────────────────────────────────────────────────────────
SECRET_KEY=your_long_random_secret_key

# ── Google Earth Engine ────────────────────────────────────────────────────
# Option A: user credentials (run `earthengine authenticate` locally)
# Option B: service account (recommended for Docker)
GEE_SERVICE_ACCOUNT_EMAIL=your-sa@project.iam.gserviceaccount.com
GEE_SERVICE_ACCOUNT_KEY_PATH=/app/secrets/gee_key.json

# ── Prithvi model ──────────────────────────────────────────────────────────
# Leave empty to auto-download from HuggingFace on first pipeline run.
# Set to a path if you have a local .pt checkpoint:
PRITHVI_MODEL_PATH=/app/models/prithvi_100m.pt

# Set to true during development to skip model inference (fast stub vectors)
PRITHVI_USE_STUB=false

# ── Optional: sklearn classification head ─────────────────────────────────
# Leave empty to use rule-based classifier (default)
CLASSIFIER_MODEL_PATH=

# ── Backups ────────────────────────────────────────────────────────────────
BACKUP_DIR=/app/backups
```

> **Never commit `.env` to version control.**

---

## Running Locally (Without Docker)

> Requires a running PostgreSQL instance (with PostGIS + pgvector) and Redis.

### 1. Create and activate a virtual environment

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 2. Install PyTorch (CPU) first, then remaining dependencies

```bash
pip install torch==2.4.1+cpu --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
```
### 3.1 SETUP the db locally
 Follow the instruction in the setup_db_locally.md file

### 3.2 Point to local services

```env
POSTGRES_HOST=localhost
REDIS_HOST=localhost
```

### 4.1 Run database migrations

```bash
alembic upgrade head
```
### 4.2 Download the data file

Go to the Resource drive and download the LakeData_Polygon file(HydroLAKES_polys_v10_shp.zip), Unzip it and copy paste the whole unziped folder in the backend/app folder.

```bash
alembic upgrade head
```

### 5. Start the API server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API: **http://localhost:8000** | Docs: **http://localhost:8000/api/docs**

---

## Running With Docker

> Recommended for the full stack — spins up PostgreSQL, Redis, and the backend API in one command.

### 1. Build and start all services

```bash
docker compose up --build
```

On first ML processing run, the backend automatically downloads the Prithvi-100M model (~400 MB) from HuggingFace and caches it in the `hf_cache` named volume. Subsequent runs load from the volume in ~15 s.

### 2. Run migrations inside the running container

```bash
docker compose exec backend alembic upgrade head
```

### 3. Verify services

| Service | URL | Description |
|---|---|---|
| API | http://localhost:8000/api/v1/health | Health check |
| Swagger UI | http://localhost:8000/api/docs | Interactive API docs |
| pgAdmin | http://localhost:8080 | PostgreSQL admin UI |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache and temporary sync status |

### 4. Docker volumes

| Volume | Purpose |
|---|---|
| `postgres_data` | PostgreSQL database files |
| `redis_data` | Redis persistence |
| `report_storage` | Generated PDF reports (`/app/reports`) |
| `sync_backups` | `pg_dump` backup files (`/app/backups`) |
| `prithvi_model` | Local `.pt` checkpoint mount (`/app/models`) |
| `hf_cache` | HuggingFace download cache (`~/.cache/huggingface`) |

### 5. Stop all services

```bash
docker compose down
```

### 6. Stop and remove all data volumes

```bash
docker compose down -v
```

> ⚠️ `-v` will also delete the `hf_cache` volume — the next start will re-download Prithvi-100M.

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback all migrations
alembic downgrade base

# Generate a new migration after model changes
alembic revision --autogenerate -m "describe_your_change"

# Show current migration state
alembic current

# Show migration history
alembic history --verbose
```

Current migrations:

| Revision | Description |
|---|---|
| `001` | Initial schema (regions, features, embeddings, temporal, reports) |
| `002` | Add `ecosystem_confidence` column to `region_features` |
| `003` | Add `state_name` column + index to `regions` |
| `004` | Refactor `regions` to lake metadata + country scope |

---

## ML Pipeline & Data Sync

### Pipeline phases (per region × year)

```
Phase 1 (GEE)        fetch_composite → NDVI / NDWI / NBR stats + band array
      ↓
Phase 2 (Prithvi)    band array → 768-dim L2-normalised embedding → pgvector
      ↓
Phase 3 (classifier) NDVI/NDWI/NBR means → ecosystem label + confidence
```

All three phases run sequentially in the backend process.

### Triggering a sync via API

```bash
# Fetch lake regions for India
GET /api/v1/regions?country=India

# Start a sync (refresh mode, India, 2020–2022)
curl -X POST http://localhost:8000/api/v1/sync/start \
  -H "Content-Type: application/json" \
  -d '{
    "country": "India",
    "duration": {"mode": "duration", "start_year": 2020, "end_year": 2022},
    "sync_mode": "refresh",
    "confirmed": true
  }'

# Poll job status
GET /api/v1/sync/status/<job_id>
```

### Time estimate

| Scope | Workers | Estimated time |
|---|---|---|
| 1 state × 1 year | 1 | ~1–1.5 min |
| 1 state × 5 years | 1 | ~5–8 min |
| 1 state × 5 years | 5 (parallel) | ~1–2 min |
| First ever run (model download) | any | +5 min one-time |

### GEE authentication

**Option A — user credentials (local dev):**
```bash
earthengine authenticate
```

**Option B — service account (Docker/production):**
1. Create a GEE-enabled service account and download the JSON key.
2. Mount the key file into the container and set:
   ```env
   GEE_SERVICE_ACCOUNT_EMAIL=sa@project.iam.gserviceaccount.com
   GEE_SERVICE_ACCOUNT_KEY_PATH=/app/secrets/gee_key.json
   ```

### Stub mode (no GEE / no GPU)

Set `PRITHVI_USE_STUB=true` in `.env` to skip real GEE calls and model inference. The pipeline uses deterministic hash-based vectors. Useful for local development; embeddings will not be meaningful for similarity search.

---

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# With coverage report
pytest --cov=app --cov-report=html
```

> Integration tests require a running PostgreSQL test database (`ecotwin_test`).  
> Set the connection string in `tests/conftest.py` to match your local setup.

---

## API Reference

All endpoints are prefixed with `/api/v1/`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/regions?country=India` | Lake regions for a country |
| `GET` | `/regions/{id}` | Region metadata + indicators |
| `POST` | `/regions/query` | Find nearest region by lat/lon |
| `GET` | `/similarity/{region_id}` | Top-K analog ecosystems |
| `GET` | `/temporal/{region_id}` | NDVI / NDWI / NBR time-series |
| `GET` | `/forecast/{region_id}` | 5-year analog-based forecast |
| `POST` | `/report` | Enqueue PDF report generation |
| `GET` | `/report/{report_id}` | Poll report status / download URL |
| `GET` | `/sync/country` | Default sync country and year bounds |
| `POST` | `/sync/start` | Start a data sync for the selected country |
| `GET` | `/sync/status/{job_id}` | Status for a completed sync job |

### Example: Find region by coordinates

```bash
curl -X POST http://localhost:8000/api/v1/regions/query \
  -H "Content-Type: application/json" \
  -d '{"lat": 28.6139, "lon": 77.2090}'
```

### Example: Search analogs

```bash
curl "http://localhost:8000/api/v1/similarity/<region_id>?top_k=10"
```

---

## Useful Scripts

```bash
# Lint and format check
ruff check app/

# Auto-fix lint issues
ruff check app/ --fix

# Type checking
mypy app/


# Watch pipeline worker logs (Docker)
docker compose logs -f pipeline_worker
```

---

## Authors

Ankit Kumar | Peeyush Prashant | Vikash Kumar
