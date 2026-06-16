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
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
- [Useful Scripts](#useful-scripts)

---

## Overview

The EcoTwin backend is a high-performance async REST API built with **FastAPI**.  
It powers:

- **Ecosystem region lookup** — nearest 5 km × 5 km grid cell for any lat/lon
- **Analog similarity search** — cosine similarity over 768-dim Prithvi embeddings via `pgvector`
- **Temporal profiles** — year-by-year NDVI / NDWI / NBR trends (2018 – present)
- **Analog-based forecasting** — 5-year outlook derived from historical twin trajectories
- **Automated PDF reports** — async generation via Celery workers

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn / Gunicorn |
| Database | PostgreSQL 16 + PostGIS + pgvector |
| ORM / Migrations | SQLAlchemy 2 (async) + Alembic |
| Cache | Redis 7 |
| Task Queue | Celery 5 + Flower (monitoring) |
| ML Embeddings | PyTorch + Prithvi Foundation Model |
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

---

## Project Structure

```
backend/
├── app/
│   ├── main.py            ← FastAPI application factory
│   ├── core/              ← Config, security, logging, exceptions, DI
│   ├── db/                ← SQLAlchemy engine & session
│   ├── models/            ← ORM models
│   ├── schemas/           ← Pydantic request / response schemas
│   ├── repositories/      ← Data access layer
│   ├── services/          ← Business logic
│   ├── api/v1/endpoints/  ← Route handlers
│   ├── cache/             ← Redis client
│   ├── workers/           ← Celery app + tasks
│   └── utils/             ← Geo utilities
├── alembic/               ← DB migration scripts
├── tests/                 ← Unit + integration tests
├── scripts/               ← Init SQL for Docker
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

### 2. Edit `.env` — set the required secrets

```env
POSTGRES_PASSWORD=your_secure_password
SECRET_KEY=your_long_random_secret_key
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

### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
```

### 3. Point to a local database

Update `.env`:

```env
POSTGRES_HOST=localhost
REDIS_HOST=localhost
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the API server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is now live at **http://localhost:8000**  
Interactive docs (dev mode): **http://localhost:8000/api/docs**

### 6. Start the Celery worker (separate terminal)

```bash
celery -A app.workers.celery_app worker --loglevel=info --queues=reports --concurrency=2
```

---

## Running With Docker

> Recommended for the full stack — spins up PostgreSQL, Redis, backend, Celery worker, and Flower in one command.

### 1. Build and start all services

```bash
docker compose up --build
```

### 2. Run migrations inside the running container

```bash
docker compose exec backend alembic upgrade head
```

### 3. Verify services

| Service | URL |
|---|---|
| API | http://localhost:8000/api/v1/health |
| API Docs (dev) | http://localhost:8000/api/docs |
| Flower (Celery) | http://localhost:5555 |

### 4. Stop all services

```bash
docker compose down
```

### 5. Stop and remove all data volumes

```bash
docker compose down -v
```

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback all migrations
alembic downgrade base

# Generate a new migration (after model changes)
alembic revision --autogenerate -m "describe_your_change"

# Show current migration state
alembic current

# Show migration history
alembic history --verbose
```

---

## Running Tests

### All tests

```bash
pytest
```

### Unit tests only

```bash
pytest tests/unit/
```

### Integration tests only

```bash
pytest tests/integration/
```

### With coverage report

```bash
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
| `GET` | `/regions/{id}` | Get region metadata + indicators |
| `POST` | `/regions/query` | Find nearest region by lat/lon |
| `GET` | `/similarity/{region_id}` | Top-K analog ecosystems |
| `GET` | `/temporal/{region_id}` | NDVI / NDWI / NBR time-series |
| `GET` | `/forecast/{region_id}` | 5-year analog-based forecast |
| `POST` | `/report` | Enqueue PDF report generation |
| `GET` | `/report/{report_id}` | Poll report status / get PDF URL |

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

# Monitor Celery tasks (Flower)
celery -A app.workers.celery_app flower --port=5555
```

---

## Authors

Ankit Kumar | Peeyush Prashant | Vikash Kumar
