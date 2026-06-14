# Docker Help — EcoTwin Backend

Installation guides and useful commands for working with Docker on Ubuntu and macOS.

---

## Table of Contents

- [Install Docker on Ubuntu](#install-docker-on-ubuntu)
- [Install Docker on macOS](#install-docker-on-macos)
- [Post-Install: Non-root Docker Access (Ubuntu)](#post-install-non-root-docker-access-ubuntu)
- [Verify Installation](#verify-installation)
- [EcoTwin Docker Compose Commands](#ecotwin-docker-compose-commands)
- [General Docker Commands](#general-docker-commands)
- [Container Management](#container-management)
- [Image Management](#image-management)
- [Volume Management](#volume-management)
- [Networking](#networking)
- [Debugging & Logs](#debugging--logs)
- [Resource Cleanup](#resource-cleanup)

---

## Install Docker on Ubuntu

> Tested on Ubuntu 22.04 LTS and 24.04 LTS.

### Step 1 — Remove old versions

```bash
sudo apt-get remove docker docker-engine docker.io containerd runc
```

### Step 2 — Install prerequisites

```bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release
```

### Step 3 — Add Docker's official GPG key

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

### Step 4 — Add the Docker repository

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### Step 5 — Install Docker Engine + Compose

```bash
sudo apt-get update
sudo apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

### Step 6 — Start and enable Docker

```bash
sudo systemctl start docker
sudo systemctl enable docker
```

---

## Install Docker on macOS

### Option A — Docker Desktop (Recommended)

1. Download **Docker Desktop for Mac** from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Double-click the `.dmg` file and drag **Docker** to Applications
3. Launch Docker from Applications — wait for the whale icon in the menu bar to stop animating
4. Docker Compose is included automatically

### Option B — Homebrew (CLI only)

```bash
# Install Homebrew first if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Docker CLI + Compose
brew install docker docker-compose
```

> Note: Homebrew installs the CLI only. You still need a container runtime — Docker Desktop or Colima.

### Option C — Colima (lightweight, no Docker Desktop)

```bash
brew install colima docker docker-compose

# Start the VM
colima start --cpu 4 --memory 8 --disk 60

# (Optional) Start automatically on login
colima start --cpu 4 --memory 8 --disk 60 --foreground false
brew services start colima
```

---

## Post-Install: Non-root Docker Access (Ubuntu)

Run Docker without `sudo`:

```bash
sudo groupadd docker           # create group if it doesn't exist
sudo usermod -aG docker $USER  # add your user
newgrp docker                  # activate without logout
```

Verify:

```bash
docker run hello-world
```

---

## Verify Installation

```bash
docker --version
docker compose version
docker run hello-world
```

---

## EcoTwin Docker Compose Commands

All commands should be run from the `backend/` directory.

```bash
# Build images and start all services in the foreground
docker compose up --build

# Start all services in the background (detached)
docker compose up -d --build

# Stop all running services
docker compose down

# Stop and remove all data volumes (full reset)
docker compose down -v

# Rebuild a single service image
docker compose build backend

# Restart a single service
docker compose restart backend

# View logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f backend
docker compose logs -f postgres
docker compose logs -f celery_worker

# Scale Celery workers
docker compose up -d --scale celery_worker=3

# Run Alembic migrations inside the backend container
docker compose exec backend alembic upgrade head

# Open an interactive shell inside a running container
docker compose exec backend bash
docker compose exec postgres psql -U ecotwin -d ecotwin

# Check service health status
docker compose ps
```

---

## General Docker Commands

```bash
# Show all running containers
docker ps

# Show all containers (including stopped)
docker ps -a

# Pull an image from Docker Hub
docker pull <image>:<tag>

# Run a container interactively
docker run -it <image> bash

# Run a container and remove it after exit
docker run --rm <image>

# Run a container in the background
docker run -d -p 8080:80 <image>

# Stop a container
docker stop <container_id_or_name>

# Start a stopped container
docker start <container_id_or_name>

# Remove a stopped container
docker rm <container_id_or_name>

# Force-remove a running container
docker rm -f <container_id_or_name>
```

---

## Container Management

```bash
# Execute a command inside a running container
docker exec -it <container> bash

# Copy a file from container to host
docker cp <container>:/path/to/file ./local/

# Copy a file from host to container
docker cp ./local/file <container>:/path/to/

# Inspect a container (full JSON metadata)
docker inspect <container>

# Check resource usage (CPU, memory)
docker stats

# View container port bindings
docker port <container>
```

---

## Image Management

```bash
# List all local images
docker images

# Build an image from a Dockerfile
docker build -t ecotwin-backend:latest .

# Build a specific stage from a multi-stage Dockerfile
docker build --target development -t ecotwin-backend:dev .
docker build --target production -t ecotwin-backend:prod .

# Tag an image
docker tag ecotwin-backend:latest myregistry/ecotwin-backend:v1.0.0

# Push an image to a registry
docker push myregistry/ecotwin-backend:v1.0.0

# Remove an image
docker rmi <image_id>

# Remove all dangling (untagged) images
docker image prune

# Remove all unused images
docker image prune -a
```

---

## Volume Management

```bash
# List all volumes
docker volume ls

# Inspect a volume
docker volume inspect ecotwin_postgres_data

# Remove a specific volume
docker volume rm ecotwin_postgres_data

# Remove all unused volumes
docker volume prune

# Backup a volume to a tar file
docker run --rm \
  -v ecotwin_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup.tar.gz /data

# Restore a volume from a tar file
docker run --rm \
  -v ecotwin_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/postgres_backup.tar.gz -C /
```

---

## Networking

```bash
# List all Docker networks
docker network ls

# Inspect a network
docker network inspect <network_name>

# Create a custom bridge network
docker network create ecotwin-net

# Connect a running container to a network
docker network connect ecotwin-net <container>

# Disconnect a container from a network
docker network disconnect ecotwin-net <container>

# Remove a network
docker network rm ecotwin-net
```

---

## Debugging & Logs

```bash
# Stream logs from a container
docker logs -f <container>

# Show last N lines of logs
docker logs --tail 100 <container>

# Show logs with timestamps
docker logs -t <container>

# Check container health status
docker inspect --format='{{.State.Health.Status}}' <container>

# Check why a container exited
docker inspect --format='{{.State.ExitCode}} {{.State.Error}}' <container>

# Run a one-off command to test connectivity
docker compose exec backend python -c "import asyncpg; print('asyncpg ok')"
docker compose exec backend python -c "import redis; r=redis.Redis(host='redis'); print(r.ping())"

# Connect to PostgreSQL inside the container
docker compose exec postgres psql -U ecotwin -d ecotwin

# List tables
\dt

# Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';

# Check PostGIS extension
SELECT PostGIS_Version();
```

---

## Resource Cleanup

```bash
# Remove all stopped containers
docker container prune

# Remove all unused images, containers, volumes, and networks
docker system prune

# Remove everything including volumes (DESTRUCTIVE — loses all data)
docker system prune -a --volumes

# Check disk usage by Docker
docker system df

# Detailed disk usage
docker system df -v
```

---

## EcoTwin Service Summary

| Container | Image | Ports | Purpose |
|---|---|---|---|
| `ecotwin_postgres` | `pgvector/pgvector:pg16` | 5432 | PostgreSQL + PostGIS + pgvector |
| `ecotwin_redis` | `redis:7.4-alpine` | 6379 | Cache + Celery broker |
| `ecotwin_backend` | `./Dockerfile` | 8000 | FastAPI REST API |
| `ecotwin_celery` | `./Dockerfile` | — | PDF report worker |
| `ecotwin_flower` | `./Dockerfile` | 5555 | Celery task monitor |
