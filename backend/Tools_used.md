## Services Overview

### Backend API
The main FastAPI application that exposes REST APIs, business logic, authentication, and data processing services.

**Port:** `8000`
**URL:** `http://localhost:8000`

---

### PostgreSQL
Primary relational database used to store application data.

Features:
- PostgreSQL database engine
- PostGIS extension for geospatial queries
- pgvector extension for vector embeddings and AI search

**Port:** `5432`

---

### Redis
In-memory data store used for:
- Caching
- Celery message broker
- Temporary data storage
- Background task queue

**Port:** `6379`

---

### Celery Worker
Background worker that executes long-running tasks asynchronously instead of blocking API requests.

Typical use cases:
- Report generation
- Data processing
- Scheduled jobs
- File exports

**No public port exposed**

---

### Flower
Web-based monitoring dashboard for Celery.

Used to:
- Monitor task execution
- View task status
- Inspect workers
- Debug failed jobs

**Port:** `5555`
**URL:** `http://localhost:5555`

---

### pgAdmin
Web-based PostgreSQL administration tool.

Used to:
- Browse databases
- Execute SQL queries
- Manage tables and indexes
- Monitor database activity

**Port:** `8080`
**URL:** `http://localhost:8080`

Default Login:
- Email: `admin@example.com`
- Password: Configured via environment variables

---

## Architecture

```text
Client
   │
   ▼
Backend API (FastAPI)
   │
   ├── PostgreSQL (Persistent Data)
   │
   ├── Redis (Cache & Queue)
   │
   └── Celery Workers (Background Tasks)
            │
            ▼
        Flower
     (Monitoring)


### Quick Understanding

| Tool | Purpose |
|--------|----------|
| **FastAPI** | Serves APIs |
| **PostgreSQL** | Stores application data |
| **Redis** | Cache and task queue |
| **Celery** | Runs background jobs |
| **Flower** | Monitors Celery tasks |
| **pgAdmin** | GUI for PostgreSQL |

This is the typical production architecture used by many Python/FastAPI applications.