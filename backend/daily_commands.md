# EcoTwin Backend - Local Setup

## Prerequisites

- Ubuntu 22.04+
- Docker Engine
- Docker Compose
- Git

---

## 1. Clone Repository

```bash
git clone <repository-url>
cd EcoTwin/backend
```

---

## 2. Configure Environment

Copy the environment file.

```bash
cp .env.example .env
```

Update the required values in `.env`.

Place the Google Earth Engine service account key at:

```
app/secrets/gee_key.json
```

---

## 3. First-Time Database Setup (Run Once)

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Enter the container:

```bash
docker exec -it ecotwin_postgres bash
```

Install pgvector:

```bash
apt-get update
apt-get install -y postgresql-16-pgvector
```

> **Note:** This setup is required **only once** on each developer's machine.

---

## 4. Start the Project

```bash
docker compose up --build -d
```

---

## 5. Apply Database Migrations

```bash
docker compose exec backend alembic upgrade head
```

---

## 6. Access Services

| Service | URL |
|----------|-----|
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/api/docs |
| pgAdmin | http://localhost:8080 |
| Flower | http://localhost:5555 |

---

# Daily Workflow

Start all services:

```bash
docker compose up -d
```

Stop all services:

```bash
docker compose down
```

View backend logs:

```bash
docker compose logs -f backend
```

View pipeline logs:

```bash
docker compose logs -f pipeline_worker
```

---

# Important Notes

- **Do NOT run** `docker compose down -v` unless you intentionally want to delete the database.
- The pgvector installation is required **only once** per machine.
- Do **not** commit `.env` or `app/secrets/gee_key.json`.

===============================================================

# Clean Start (Only if you previously ran an older setup)

If you have previously run EcoTwin and encountered Docker errors, reset your local environment before following the setup guide.

## 1. Stop all running containers

```bash
docker compose down
```

---

## 2. Remove old EcoTwin containers

```bash
docker compose down --remove-orphans
```

---

## 3. Remove old Docker images (EcoTwin only)

```bash
docker compose down --rmi local
```

---

## 4. Remove old volumes (Deletes the database)

> **Warning:** This permanently deletes your local PostgreSQL database.

```bash
docker compose down -v
```

---

## 5. Remove unused Docker resources

```bash
docker system prune -f
```

(Optional)

```bash
docker volume prune -f
```
