# EcoTwin — Backend Architecture

A detailed technical reference for the backend codebase structure, design patterns,
data flow, and component responsibilities.

---

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [High-Level Architecture](#high-level-architecture)
- [Layer Overview](#layer-overview)
- [Folder & File Reference](#folder--file-reference)
  - [app/core/](#appcore)
  - [app/db/](#appdb)
  - [app/models/](#appmodels)
  - [app/schemas/](#appschemas)
  - [app/repositories/](#apprepositories)
  - [app/services/](#appservices)
  - [app/api/](#appapi)
  - [app/cache/](#appcache)
  - [app/workers/](#appworkers)
  - [app/utils/](#apputils)
  - [alembic/](#alembic)
  - [tests/](#tests)
  - [Root-level files](#root-level-files)
- [Data Flow — Request Lifecycle](#data-flow--request-lifecycle)
- [Database Schema Design](#database-schema-design)
- [Similarity Search Design](#similarity-search-design)
- [Analog Forecasting Engine](#analog-forecasting-engine)
- [Async Report Generation Pipeline](#async-report-generation-pipeline)
- [Caching Strategy](#caching-strategy)
- [Security Design](#security-design)
- [TODO (Manual)](#todo-manual)

---

## Design Philosophy

1. **Layered architecture** — strict separation between HTTP routing, business logic, and data access. No SQL in endpoints; no HTTP in services.
2. **Async-first** — API database access uses `asyncpg` via SQLAlchemy's async engine; the ML pipeline uses a synchronous engine outside that session.
3. **Repository pattern** — services never touch SQLAlchemy queries directly; they call typed repository methods. This makes testing and future DB swaps easier.
4. **Graceful degradation** — Redis cache failures silently fall back to direct DB queries. The system stays functional without cache.
5. **Explainability** — the forecasting engine derives predictions from real historical analog trajectories, not black-box models. Every forecast includes a human-readable explanation.

---

## High-Level Architecture

```
                      ┌─────────────────────────────────┐
                      │         React Frontend           │
                      └────────────────┬────────────────┘
                                       │ HTTP / REST
                      ┌────────────────▼────────────────┐
                      │         Nginx Reverse Proxy       │
                      └────────────────┬────────────────┘
                                       │
                      ┌────────────────▼────────────────┐
                      │       FastAPI Backend (Uvicorn)   │
                      │                                   │
                      │  ┌──────────┐  ┌──────────────┐  │
                      │  │ API Layer│  │  Middleware   │  │
                      │  └────┬─────┘  │  CORS / GZip │  │
                      │       │        └──────────────┘  │
                      │  ┌────▼─────┐                     │
                      │  │ Services │                     │
                      │  └────┬─────┘                     │
                      │       │                           │
                      │  ┌────▼──────────┐               │
                      │  │ Repositories  │               │
                      │  └────┬──────────┘               │
                      └───────┼──────────────────────────┘
                              │
              ┌───────────────┼──────────────────┐
              │               │                  │
    ┌─────────▼──────┐  ┌─────▼──────┐  ┌────────▼──────┐
    │  PostgreSQL 16  │  │  pgvector  │  │  Redis 7      │
    │  + PostGIS      │  │  (cosine   │  │  (cache +     │
    │  (spatial data) │  │   index)   │  │   broker)     │
    └────────────────┘  └────────────┘  └───────────────┘
                                                │
                                      ┌─────────▼──────┐
                                      │ ML Processing   │
                                      │  (PDF reports)  │
                                      └────────────────┘
```

---

## Layer Overview

```
Request → Endpoint → Service → Repository → Database
                 ↕                    ↕
              Schemas              Models
                 ↕
              Cache (Redis)
```

| Layer | Location | Responsibility |
|---|---|---|
| **Entry point** | `app/main.py` | App factory, middleware, exception handlers |
| **Routing** | `app/api/v1/` | URL dispatch, HTTP status codes, request parsing |
| **Business logic** | `app/services/` | Orchestration, domain rules, algorithm logic |
| **Data access** | `app/repositories/` | SQL queries, pgvector search, DB writes |
| **ORM models** | `app/models/` | SQLAlchemy table definitions |
| **Validation** | `app/schemas/` | Pydantic input/output contracts |
| **Config & cross-cutting** | `app/core/` | Settings, security, logging, DI, exceptions |
| **Cache** | `app/cache/` | Redis abstraction |
| **Processing** | `app/ML_pipeline/` | In-process ML pipeline and task definitions |

---

## Folder & File Reference

### `app/core/`

The foundation layer. Nothing in this package imports from `app.models`, `app.services`, or `app.repositories`.

| File | Purpose |
|---|---|
| `config.py` | `Settings` class backed by `pydantic-settings`. Reads `.env`, exposes typed fields. Computed `DATABASE_URL`, `REDIS_URL`. Cached with `@lru_cache`. |
| `security.py` | `create_access_token()` / `decode_access_token()` using `python-jose`. `hash_password()` / `verify_password()` using `passlib bcrypt`. |
| `logging.py` | Configures `structlog`. JSON output in production; coloured console in debug mode. Suppresses noisy library loggers. |
| `exceptions.py` | Domain exception hierarchy (`EcoTwinBaseException` → `NotFoundException` → `RegionNotFoundException`, etc.). Every exception carries `status_code`, `code`, and `message`. |
| `dependencies.py` | FastAPI `Annotated` dependency aliases: `DatabaseDep`, `CacheDep`, `CurrentUserDep`. Centralises injection so endpoints stay concise. |

---

### `app/db/`

| File | Purpose |
|---|---|
| `base.py` | Shared `DeclarativeBase`. All ORM models inherit from this so Alembic can discover them via `Base.metadata`. |
| `session.py` | Creates the async SQLAlchemy engine with connection pooling (`pool_size=10`, `max_overflow=20`). Exposes `get_db()` — a FastAPI dependency that yields an `AsyncSession` with automatic commit/rollback. |

---

### `app/models/`

SQLAlchemy ORM table definitions. All use `UUID` primary keys.

| File | Tables | Key Columns |
|---|---|---|
| `region.py` | `regions`, `region_features` | `regions`: `region_id`, `center_lat`, `center_lon`, `geom (PostGIS POLYGON)`. `region_features`: NDVI/NDWI/NBR statistics per year. |
| `embedding.py` | `region_embeddings` | `region_id`, `year`, `embedding VECTOR(768)` — the 768-dim Prithvi output. |
| `temporal_profile.py` | `temporal_profiles` | `region_id`, `year`, `ndvi`, `ndwi`, `nbr` — annual scalar indicator values for the forecast engine. |
| `report.py` | `reports` | `report_id`, `region_id`, `status` (pending/processing/completed/failed), `pdf_url`. |
| `__init__.py` | — | Re-exports all models so `import app.models` is enough for Alembic to detect all tables. |

---

### `app/schemas/`

Pydantic v2 models for API contracts. Decoupled from ORM models to allow independent evolution.

| File | Schemas | Notes |
|---|---|---|
| `common.py` | `HealthResponse`, `ErrorResponse`, `PaginatedResponse[T]` | Generic paginated wrapper. |
| `region.py` | `RegionResponse`, `RegionFeatureResponse`, `RegionQueryRequest`, `RegionQueryResponse`, `RegionSummaryResponse` | `RegionQueryRequest` validates lat ∈ [-90, 90], lon ∈ [-180, 180]. |
| `similarity.py` | `AnalogResult`, `SimilaritySearchResponse` | `similarity_score` clamped to [0, 1]. Includes `search_latency_ms`. |
| `forecast.py` | `YearlyIndicator`, `TemporalDataResponse`, `ForecastHorizon`, `ForecastResponse` | `ForecastResponse` includes human-readable `explanation` and directional trend labels. |
| `report.py` | `ReportGenerateRequest`, `ReportResponse` | Request validates `top_k_analogs` ∈ [1, 20]. Response mirrors DB report row. |

---

### `app/repositories/`

All database I/O. Services call repositories; repositories never call services.

| File | Class | Key Methods |
|---|---|---|
| `base_repository.py` | `BaseRepository[T]` | `save(instance)`, `delete(instance)` — generic flush + refresh helpers. |
| `region_repository.py` | `RegionRepository` | `get_by_id()`, `find_nearest(lat, lon)` (Euclidean approx for speed), `get_latest_features()`, `count()`. |
| `embedding_repository.py` | `EmbeddingRepository` | `get_by_region_year()`, `get_latest()`, `search_similar()` — the core pgvector cosine search using raw `text()` SQL to hit the IVFFlat index. Returns `(rows, latency_ms)`. |
| `feature_repository.py` | `FeatureRepository` | `get_by_region_year()`, `get_all_years()` — fetch full NDVI/NDWI/NBR history for a region. |
| `temporal_repository.py` | `TemporalRepository` | `get_profile(region_id)` — returns sorted annual time-series used by the forecast engine. |

---

### `app/services/`

Business logic. No FastAPI imports; services can be tested independently of HTTP.

| File | Class | Responsibility |
|---|---|---|
| `region_service.py` | `RegionService` | Wraps region + feature queries. Computes haversine distance for the `find_region_by_coordinates` response. |
| `similarity_service.py` | `SimilarityService` | Resolves the query embedding, invokes `EmbeddingRepository.search_similar()`, clamps scores, logs latency. |
| `forecast_service.py` | `ForecastService` | Loads target temporal profile + best analog trajectory. Projects analog deltas forward as a 5-year forecast. Computes per-year confidence (decays with horizon). Determines trend labels (`increasing` / `stable` / `declining`) from recent slope. Falls back gracefully when no analog exists. |
| `report_service.py` | `ReportService` | Creates a `Report` DB row and generates the PDF directly. |

---

### `app/api/`

HTTP layer only. No business logic; delegates entirely to services.

```
app/api/
└── v1/
    ├── router.py          ← Aggregates all endpoint routers under /api/v1
    └── endpoints/
        ├── health.py      ← GET /health
        ├── regions.py     ← GET /regions/{id}, POST /regions/query
        ├── similarity.py  ← GET /similarity/{region_id}?top_k=&year=
        ├── temporal.py    ← GET /temporal/{region_id}
        ├── forecast.py    ← GET /forecast/{region_id}
        └── reports.py     ← POST /report, GET /report/{report_id}
```

**Pattern used in every endpoint file:**
1. Declare a local `_service(db)` factory function as a `Depends()` target
2. Inject `DatabaseDep` and `CacheDep` via `Annotated` type aliases from `core/dependencies.py`
3. Check Redis cache → call service → write to Redis → return

---

### `app/cache/`

| File | Class | Notes |
|---|---|---|
| `redis_client.py` | `RedisClient` | `get()`, `set()`, `delete()`, `invalidate_pattern()`. All methods catch exceptions and log warnings — never raises to the caller, enabling graceful degradation. `get_redis_client()` is a FastAPI dependency that returns `None` if Redis is unreachable. |

---

### `app/workers/`

| File | Purpose |
|---|---|
| `report_generator.py` | Builds a PDF with ReportLab and persists it to local storage (or S3). |

---

### `app/utils/`

| File | Functions | Purpose |
|---|---|---|
| `geo_utils.py` | `haversine_km()`, `bbox_from_center()`, `bbox_to_wkt()`, `center_to_grid_wkt()` | Pure geometry helpers. Convert a grid cell centre into a WKT polygon for DB storage. Compute great-circle distances. |

---

### `alembic/`

| File / Folder | Purpose |
|---|---|
| `alembic.ini` | Alembic configuration. Points at the `alembic/` script directory. |
| `env.py` | Async migration runner. Imports `Base.metadata` and `app.models` to ensure all tables are discovered. Uses `settings.DATABASE_URL` (async) for online mode, `settings.SYNC_DATABASE_URL` for offline mode. |
| `script.py.mako` | Template for auto-generated revision files. |
| `versions/001_initial_schema.py` | Initial migration: enables `postgis` + `vector` extensions; creates all 5 tables; creates `IVFFlat` cosine index on `region_embeddings.embedding` with `lists=100`. |

---

### `tests/`

```
tests/
├── conftest.py                         ← Shared fixtures: engine, session, HTTP client
├── unit/
│   └── test_services/
│       └── test_forecast_service.py    ← _trend() function tests (no DB needed)
└── integration/
    └── test_api/
        └── test_regions.py            ← HTTP-level tests against real DB
```

| File | What it tests |
|---|---|
| `conftest.py` | Creates test DB schema in a session-scoped engine. Each test gets a transaction-rolled-back session. Overrides `get_db` dependency. |
| `test_forecast_service.py` | Pure unit tests for the `_trend()` helper — covers all edge cases (empty, single, two values, multi-value). |
| `test_regions.py` | Integration: health endpoint returns 200; unknown region returns 404; invalid coordinates return 422. |

---

### Root-level files

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build. `base` → installs system libs + Python deps. `development` → adds dev deps, runs with `--reload`. `production` → non-root user, Gunicorn + UvicornWorker, 4 workers. |
| `docker-compose.yml` | Defines `postgres`, `redis`, `backend`, and `pgadmin`. Healthchecks on postgres and redis; backend waits for them. Named volumes provide data persistence. |
| `requirements.txt` | Production dependencies (pinned versions). |
| `requirements-dev.txt` | Extends `requirements.txt` with pytest, ruff, mypy, pre-commit. |
| `pyproject.toml` | Ruff (lint/format), pytest (asyncio auto mode, coverage), mypy configuration. |
| `.env.example` | Template for `.env`. Documents every required variable. |
| `scripts/init_db.sql` | SQL executed by PostgreSQL container on first boot. Enables `postgis` and `vector` extensions. |
| `alembic.ini` | Alembic entry-point config. |

---

## Data Flow — Request Lifecycle

### Example: `GET /api/v1/similarity/{region_id}?top_k=10`

```
1. Nginx → FastAPI (Uvicorn)
2. CORS middleware
3. GZip middleware
4. Router: routes to similarity.py endpoint handler
5. FastAPI dependency injection:
     └─ get_db()          → AsyncSession
     └─ get_redis_client() → RedisClient | None
6. Endpoint: build cache key "similarity:{region_id}:None:10"
7. RedisClient.get(key)
     ├─ HIT  → deserialise JSON → return SimilaritySearchResponse (< 5 ms)
     └─ MISS ↓
8. SimilarityService.search_analogs(region_id, top_k=10)
     ├─ RegionRepository.get_by_id()        → validates region exists
     ├─ EmbeddingRepository.get_latest()    → fetches 768-dim vector
     └─ EmbeddingRepository.search_similar() → pgvector IVFFlat cosine scan
           └─ raw SQL: ORDER BY embedding <=> $vec LIMIT 10
9. Service: builds SimilaritySearchResponse with AnalogResult list
10. Endpoint: RedisClient.set(key, json, ttl=86400)
11. FastAPI: serialises response → JSON → 200 OK
12. Total target latency: < 500 ms
```

---

## Database Schema Design

```
regions (1)
    │
    ├──< region_features     (one row per region per year — NDVI/NDWI/NBR stats)
    ├──< region_embeddings   (one row per region per year — VECTOR(768))
    ├──< temporal_profiles   (one row per region per year — scalar indicators)
    └──< reports             (one row per report job)
```

**Critical index:**
```sql
CREATE INDEX idx_region_embedding_cosine
ON region_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```
This allows pgvector to perform approximate nearest-neighbour search in sub-linear time.
`lists = 100` is a starting point; optimal value ≈ `sqrt(num_rows)`.

---

## Similarity Search Design

```
Query embedding (768 dims)
         │
         ▼
pgvector IVFFlat index
  cosine distance: e1 <=> e2
         │
         ▼
Top-K rows (region_id, year, similarity_score)
         │
         ▼
JOIN regions  →  center_lat, center_lon
JOIN region_features  →  dominant_ecosystem
         │
         ▼
SimilaritySearchResponse
```

- **Metric:** cosine similarity = 1 − cosine distance
- **Default K:** 10 (configurable up to `MAX_TOP_K = 50`)
- **Target latency:** < 500 ms for K = 10 across thousands of regions
- **Cache TTL:** 24 hours (embeddings change only when re-ingested)

---

## Analog Forecasting Engine

```
Target region (current year Y)
         │
         ▼
Search top-5 analogs (same as similarity search)
         │
         ▼
Best analog A matched at historical year Y_a
         │
         ▼
For forecast horizon i = 1..5:
    analog_future = temporal_profiles[A, Y_a + i]
    confidence    = similarity_score × decay(i)
    ├─ analog future exists → use its NDVI/NDWI/NBR
    └─ missing → fallback to target's last known value × 0.5 confidence
         │
         ▼
ForecastResponse (5 ForecastHorizon objects + overall stats)
```

**Confidence decay formula:**
```
confidence(i) = similarity_score × max(0.3, 1.0 − (i − 1) × 0.08)
```
At horizon 5 the raw score is multiplied by 0.68 (32% decay).

**Trend detection:**
```python
slope = (recent[-1] − recent[0]) / (len(recent) − 1)
"increasing" if slope > 0.01
"declining"  if slope < −0.01
"stable"     otherwise
```

---

## Async Report Generation Pipeline

```
POST /report
     │
     ▼
ReportService.create_report_job()
     ├─ Creates Report row (status=PENDING)
     ├─ Generates report directly
     └─ Returns ReportResponse (status=PROCESSING)

               │  (async, separate worker process)
               ▼
     report_generator
          ├─ _build_pdf()    → ReportLab → bytes
          ├─ _persist_pdf()  → writes to /app/reports/<id>.pdf
          └─ _update_report_db() → status=COMPLETED, pdf_url=...

GET /report/{id}
     └─ Returns current status + pdf_url when ready
```

The ML pipeline uses a **synchronous** SQLAlchemy engine (`SYNC_DATABASE_URL`) outside the API's async database session.

---

## Caching Strategy

| Cache Key | Value | TTL |
|---|---|---|
| `similarity:{region_id}:{year}:{top_k}` | `SimilaritySearchResponse` JSON | 24 h |
| `forecast:{region_id}` | `ForecastResponse` JSON | 24 h |

**Invalidation:** when new embeddings are ingested for a region, call `RedisClient.invalidate_pattern(f"similarity:{region_id}:*")` and `del forecast:{region_id}`.

---

## Security Design

| Concern | Implementation |
|---|---|
| Authentication | JWT Bearer tokens (`python-jose`, HS256) |
| Password storage | bcrypt via `passlib` (never stored as plain text) |
| Rate limiting | To be implemented via Nginx or a FastAPI middleware |
| CORS | Whitelist-based (`ALLOWED_ORIGINS` in `.env`) |
| Docs exposure | OpenAPI / Swagger UI disabled in production (`DEBUG=false`) |
| Container security | Non-root user (`appuser`) in production Docker image |
| Secrets | All secrets via `.env` — never hardcoded or committed |

---

## TODO (Manual)

This section tracks known gaps and planned improvements.
Update manually as items are completed or new ones are identified.

### High Priority

- [ ] **ML pipeline integration** — wire the Prithvi model inference script; currently embeddings must be pre-computed and loaded via the data pipeline
- [ ] **Data ingestion script** — `data_pipeline/` module for Google Earth Engine → PostgreSQL ETL (Sentinel-2 composite → NDVI/NDWI/NBR → Prithvi embedding → DB insert)
- [ ] **Authentication endpoints** — `POST /auth/login`, `POST /auth/register`, `POST /auth/refresh`; currently JWT decode is wired but no user table or login endpoint exists
- [ ] **User model** — add `users` table, FK on `reports.user_id`, role-based access (researcher / admin)
- [ ] **Rate limiting** — add per-user request limits (recommend `slowapi` or Nginx `limit_req`)

### Medium Priority

- [ ] **S3 report storage** — swap `_persist_pdf()` local file write for `boto3` S3 upload when `S3_BUCKET` is set
- [ ] **PostGIS spatial query** — replace the Euclidean approximation in `RegionRepository.find_nearest()` with a proper `ST_DWithin` / `ST_Distance` spatial query
- [ ] **IVFFlat `lists` tuning** — once the full region dataset is loaded, re-create the cosine index with `lists = sqrt(total_rows)` for optimal recall/speed tradeoff
- [ ] **Prometheus metrics endpoint** — expose `/metrics` for Grafana dashboards (API latency, search latency, error rates)
- [ ] **Pagination** — add `page` / `page_size` to `GET /regions` list endpoint (not yet implemented)
- [ ] **OpenAPI security scheme** — annotate protected endpoints with `HTTPBearer` security in the OpenAPI schema

### Low Priority

- [ ] **Scheduled cache refresh** — refresh stale cache entries overnight
- [ ] **Pre-commit hooks** — finalise `.pre-commit-config.yaml` with ruff + mypy hooks
- [ ] **Fixture data** — add `scripts/seed_sample_data.py` with a small synthetic dataset for local development without running the full GEE pipeline
- [ ] **CI/CD pipeline** — GitHub Actions workflow: lint → test → build Docker image → push to registry
- [ ] **Kubernetes manifests** — `k8s/` folder with Deployments, Services, PVC, ConfigMap for production cloud deployment
- [ ] **Integration test coverage** — expand `tests/integration/` to cover similarity, forecast, and report endpoints end-to-end
- [ ] **Async cache invalidation** — background task to purge stale similarity/forecast cache entries when embeddings are re-ingested

### Completed

- [x] Core FastAPI app factory with lifespan, CORS, GZip, exception handlers
- [x] Async SQLAlchemy engine + session with connection pooling
- [x] ORM models — regions, features, embeddings, temporal profiles, reports
- [x] Pydantic v2 schemas — all request/response contracts
- [x] Repository layer — generic base + domain-specific repos
- [x] pgvector IVFFlat cosine similarity search with latency measurement
- [x] Analog-based 5-year forecast engine with confidence scoring
- [x] Redis cache with graceful degradation
- [x] PDF report generation
- [x] Alembic migration — initial schema with all extensions and indexes
- [x] Multi-stage Dockerfile (dev + production with non-root user)
- [x] Docker Compose — full stack (postgres, redis, backend, pgadmin)
- [x] Unit tests — forecast trend helper
- [x] Integration tests — health, 404, 422 validation
