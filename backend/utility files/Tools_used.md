## Services Overview

### Backend API

FastAPI application exposing REST APIs, business logic, authentication, and data processing.

**Port:** `8000`
**URL:** `http://localhost:8000`

### PostgreSQL

Primary relational database, with PostGIS for geospatial data and pgvector for vector search.

**Port:** `5432`

### Redis

In-memory data store used for caching and temporary sync-status data.

**Port:** `6379`

### pgAdmin

Web-based PostgreSQL administration tool.

**Port:** `8080`
**URL:** `http://localhost:8080`

## Architecture

```text
Client
   │
   ▼
Backend API (FastAPI)
   ├── PostgreSQL (persistent data)
   ├── Redis (cache and temporary status)
   └── Report and ML processing
```

| Tool | Purpose |
| --- | --- |
| FastAPI | Serves APIs and runs application processing |
| PostgreSQL | Stores application data |
| Redis | Caches data and stores temporary sync status |
| pgAdmin | PostgreSQL administration UI |
