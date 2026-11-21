# AutoHeal DevOps — Docker Infrastructure & Setup Guide

This document describes the multi-stage containerization, security policies, and Docker Compose environments for AutoHeal DevOps.

---

## 1. Containerization Architecture

AutoHeal DevOps utilizes production-grade, multi-stage Docker builds designed for minimal image size, immutability, and defense-in-depth isolation.

### 1.1 Multi-Stage Container Specifications

| Container / Service | Base Image | Multi-Stage Target | Unprivileged User | Healthcheck Probe |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend** (`Dockerfile`) | `node:20-alpine` | Next.js standalone runner | `nextjs` (UID 1001) | HTTP GET `http://127.0.0.1:3000/` |
| **FastAPI Backend** (`backend/Dockerfile`) | `python:3.12-slim` | Two-stage wheel builder + runner | `autoheal` (UID 10001) | HTTP GET `http://127.0.0.1:8000/api/v1/health` |
| **Celery Worker** (`backend/Dockerfile.celery_worker`) | `python:3.12-slim` | Worker runner | `autoheal` (UID 10001) | Python `celery_app.control.ping()` |
| **Celery Beat** (`backend/Dockerfile.celery_beat`) | `python:3.12-slim` | Beat scheduler runner | `autoheal` (UID 10001) | Process liveness check |
| **PostgreSQL** (`db`) | `postgres:16-alpine` | Official hardened Alpine | `postgres` (UID 70) | `pg_isready -U postgres -d autoheal_db` |
| **Redis** (`redis`) | `redis:7-alpine` | Official Alpine | `redis` (UID 999) | `redis-cli ping` |

---

## 2. Infrastructure Security Standards

1. **Zero Docker Socket Exposure**:
   - The host Docker socket (`/var/run/docker.sock`) is **STRICTLY NEVER** mounted into any web application, Celery worker, or recovery executor container.
   - Remediation actions are executed via cryptographically signed HTTP/mTLS control-plane requests or simulation adapters, completely preventing container breakout risks.

2. **Unprivileged Non-Root Execution**:
   - All custom containers explicitly switch to non-root system users (`USER autoheal` / `USER nextjs`) before starting any runtime process.
   - Sudo access and package managers are excluded from final runtime stages.

3. **Isolated Networking**:
   - Containers communicate over an isolated internal bridge network (`autoheal_network`).
   - In production, PostgreSQL (`5432`) and Redis (`6379`) do **not** publish ports to host interfaces.

4. **Secret Hygiene**:
   - `.dockerignore` strictly excludes `.env*`, `.git`, `.venv`, `node_modules`, `backups`, and database files to prevent credential leakage into container layers.

---

## 3. Docker Compose Configurations

### 3.1 Production Stack (`docker-compose.yml`)

The production compose environment orchestrates 11 microservices:
1. `frontend`: Next.js production web UI (Port `3000:3000`).
2. `backend`: FastAPI asynchronous REST API (Port `8000:8000`).
3. `db`: PostgreSQL 16 relational database with persistent named volume `pgdata`.
4. `redis`: Redis 7 task broker & cache with persistent named volume `redisdata`.
5. `celery_worker`: Distributed background task executor (`--concurrency=4`).
6. `celery_beat`: Periodic scheduler for telemetry cycles.
7. `prometheus`: Metrics collection and rule evaluation (Port `9090:9090`).
8. `alertmanager`: Webhook alert router with HMAC authentication (Port `9093:9093`).
9. `grafana`: Observability dashboards (Port `3001:3000`).
10. `node_exporter`: Host hardware and OS metric collector (Port `9100:9100`).
11. `cadvisor`: Container metrics exporter (Port `8081:8080`).

### 3.2 Development Stack (`docker-compose.dev.yml`)

Optimized for local iteration:
- Hot-reloading enabled for FastAPI backend (`./backend:/app`).
- Host port exposures for inspection (`5432:5432` for PostgreSQL, `6379:6379` for Redis).
- Local simulation defaults preconfigured.

---

## 4. Operational Commands (PowerShell / Bash)

### 4.1 Validate Configuration Syntax
```powershell
docker compose -f docker-compose.yml config
docker compose -f docker-compose.dev.yml config
```

### 4.2 Start Infrastructure in Background
```powershell
# Production stack
docker compose -f docker-compose.yml up -d

# Development stack
docker compose -f docker-compose.dev.yml up -d
```

### 4.3 Monitor Container Health
```powershell
docker compose ps
```

Example healthy output:
```text
NAME                     IMAGE                      STATUS                    PORTS
autoheal-backend         autoheal-backend:latest    Up (healthy) 8000/tcp     0.0.0.0:8000->8000/tcp
autoheal-db              postgres:16-alpine         Up (healthy) 5432/tcp     
autoheal-frontend        autoheal-frontend:latest   Up (healthy) 3000/tcp     0.0.0.0:3000->3000/tcp
autoheal-redis           redis:7-alpine             Up (healthy) 6379/tcp     
autoheal-celery-worker   autoheal-worker:latest     Up (healthy)              
autoheal-prometheus      prom/prometheus:latest     Up 9090/tcp               0.0.0.0:9090->9090/tcp
autoheal-alertmanager    prom/alertmanager:latest   Up 9093/tcp               0.0.0.0:9093->9093/tcp
```

### 4.4 View Logs
```powershell
# Follow backend logs
docker compose logs -f backend

# Follow Celery worker logs
docker compose logs -f celery_worker
```

### 4.5 Stop and Clean Up
```powershell
# Stop containers gracefully
docker compose stop

# Tear down containers preserving persistent data volumes
docker compose down

# Tear down containers and remove volumes (DESTRUCTIVE)
docker compose down -v
```

---

## 5. Docker Desktop on Windows & WSL2 Notes

- **Linux Engine Named Pipe**: Docker Desktop for Windows requires the Linux VM engine to be initialized. Verify with `docker info`.
- **Node Exporter Host Root Mount**: On Docker Desktop (WSL2), root bind mounts (`/host/root`) are configured with appropriate mount flags (`ro,rslave` or containerized abstractions) to avoid Windows bind-mount incompatibilities.
- **File Watching**: When developing inside WSL2 or Windows, ensure volume mounts point to the Linux filesystem or utilize polling mode if changes are not detected immediately.
