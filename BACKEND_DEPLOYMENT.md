# AutoHeal DevOps — Production Backend Deployment Guide

This document provides a comprehensive runbook for deploying the AutoHeal DevOps backend infrastructure to production cloud environments.

---

## 1. Cloud Architecture Overview

The AutoHeal DevOps production backend consists of four primary components:

1. **FastAPI Web Service**: High-performance asynchronous API server running under Uvicorn with ASGI reverse-proxy support. Handles REST API requests, WebSocket telemetry, Alertmanager webhooks, and JWT/cookie authentication.
2. **PostgreSQL 16 Managed Database**: Relational storage for user profiles, organizations, services, metrics, incidents, audit logs, and refresh token families.
3. **Redis 7 Managed In-Memory Store**: Asynchronous task queue broker and results backend for Celery, rate-limiting store, and real-time cache.
4. **Celery Worker & Celery Beat**:
   - `autoheal-celery-worker`: Distributed worker process executing async self-healing workflows, incident diagnosis, and automated actions.
   - `autoheal-celery-beat`: Periodic task scheduler driving metric aggregation, SLA monitoring, and node heartbeat checks.

```
                            [ Live Vercel Frontend ]
                           (autoheal-omega.vercel.app)
                                       │
                                       │ HTTPS / WSS (REST & Telemetry)
                                       ▼
                       [ Cloud Load Balancer / Proxy ]
                         (TLS 1.3 Termination, HSTS)
                                       │
                                       ▼
                     [ FastAPI Backend (Uvicorn ASGI) ]
                         Port: $PORT (non-root autoheal)
                         Probes: /api/v1/health, /health/readiness
                                │            │
               ┌────────────────┘            └────────────────┐
               ▼                                              ▼
    [ Managed PostgreSQL 16 ]                        [ Managed Redis 7 ]
      (SSL/TLS: sslmode=require)                       (TLS: rediss://...)
               ▲                                              ▲
               │                                              │
               ├───────────────────┐                          │
               │                   ▼                          │
    [ Celery Worker Pool ] ◄────────────── [ Celery Beat Scheduler ]
    (Async Remediations)                    (Periodic Monitoring)
```

---

## 2. Deployment Options

### Option A: Render Blueprint Deployment (Recommended)

Render provides native infrastructure-as-code orchestration via `render.yaml`.

#### Step 1: Link Repository and Apply Blueprint
1. Log in to the [Render Dashboard](https://dashboard.render.com).
2. Click **New +** > **Blueprint**.
3. Select the repository: `https://github.com/HMSLBDN/Autoheal.git` (branch: `main`).
4. Render parses `render.yaml` and plans four services:
   - `autoheal-backend` (Docker Web Service)
   - `autoheal-celery-worker` (Docker Background Worker)
   - `autoheal-celery-beat` (Docker Background Worker)
   - `autoheal-db` (PostgreSQL 16 Managed Database)
   - `autoheal-redis` (Redis 7 Managed Instance)
5. Review the plan and click **Apply**.

#### Step 2: Automated Migrations and Startup
- The backend configuration includes an automated `preDeployCommand`:
  ```bash
  alembic upgrade head
  ```
  Render runs this command in an isolated release container before routing public traffic to the new deployment. If migrations fail, the deployment is aborted safely without downtime.

#### Step 3: Initial Data Seeding (First-time setup only)
After the first successful deployment:
1. Navigate to **`autoheal-backend`** > **Shell**.
2. Run the idempotent database seeder:
   ```bash
   python seed.py
   ```
3. Verify output:
   ```text
   [seed] Connected to database.
   [seed] Baseline roles and test services successfully seeded.
   ```

---

### Option B: Railway Deployment

Railway supports multi-service projects with automatic private networking.

#### Step 1: Create Project & Provision Data Stores
1. Create a new empty project in Railway.
2. Add a **PostgreSQL** service (version 16).
3. Add a **Redis** service (version 7).

#### Step 2: Deploy the FastAPI Backend
1. Click **New** > **GitHub Repo** > Select `HMSLBDN/Autoheal`.
2. In the service settings:
   - **Root Directory**: `.`
   - **Dockerfile Path**: `backend/Dockerfile`
   - **Healthcheck Path**: `/api/v1/health`
3. Configure Environment Variables:
   - `DATABASE_URL`: Set to `${{Postgres.DATABASE_URL}}`
   - `REDIS_URL`: Set to `${{Redis.REDIS_URL}}`
   - `SECRET_KEY`: Generate a 64-character hex string (`openssl rand -hex 32`)
   - `CORS_ORIGINS`: `["https://autoheal-omega.vercel.app"]`
   - `COOKIE_SECURE`: `true`
   - `COOKIE_SAMESITE`: `none`
   - `APP_ENV`: `production`

#### Step 3: Deploy Celery Worker and Beat
1. Add another service from the same repository for the Worker:
   - **Dockerfile Path**: `backend/Dockerfile`
   - **Custom Start Command**: `celery -A app.worker.celery_app worker --loglevel=info --concurrency=4`
   - Inherit `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `APP_ENV`.
2. Add a third service for Celery Beat:
   - **Dockerfile Path**: `backend/Dockerfile`
   - **Custom Start Command**: `celery -A app.worker.celery_app beat --loglevel=info`
   - Inherit `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `APP_ENV`.

#### Step 4: Run Alembic Migrations
In the `autoheal-backend` service on Railway, run the migration via Railway CLI or one-off command:
```bash
railway run alembic upgrade head
railway run python seed.py
```

---

### Option C: Fly.io Deployment

Fly.io runs applications in lightweight Firecracker microVMs across global edge locations.

#### Step 1: Provision Postgres and Redis
```bash
# Provision Postgres
fly postgres create --name autoheal-db --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x

# Provision Redis (Upstash Redis)
fly redis create --name autoheal-redis --region iad
```

#### Step 2: Deploy Backend App
1. Initialize the app:
   ```bash
   fly launch --dockerfile backend/Dockerfile --name autoheal-backend --no-deploy
   ```
2. Set configuration secrets:
   ```bash
   fly secrets set \
     SECRET_KEY=$(openssl rand -hex 32) \
     DATABASE_URL="postgres://..." \
     REDIS_URL="rediss://..." \
     CORS_ORIGINS='["https://autoheal-omega.vercel.app"]' \
     COOKIE_SECURE="true" \
     COOKIE_SAMESITE="none" \
     APP_ENV="production"
   ```
3. Set the release command in `fly.toml`:
   ```toml
   [deploy]
     release_command = "alembic upgrade head"
   ```
4. Deploy:
   ```bash
   fly deploy
   ```

---

## 3. Database SSL/TLS Connection Handling

Cloud databases (Neon, Supabase, AWS RDS, Render Postgres) enforce SSL/TLS connections and commonly provide connection strings with `?sslmode=require`.

### Asyncpg Compatibility
Python's `asyncpg` driver does not accept the `sslmode` query parameter directly and requires `ssl=require`.

The AutoHeal application (`backend/app/config.py`) automatically translates this in `assemble_database_url`:
- `?sslmode=require` $\to$ `?ssl=require`
- `?sslmode=prefer` $\to$ `?ssl=prefer`
- `?sslmode=disable` $\to$ `?ssl=disable`

No manual URL rewriting is required; you can paste the standard provider connection string directly into `DATABASE_URL`.

---

## 4. Zero-Downtime Health Probes

The FastAPI backend exposes three levels of health endpoints for orchestrator probes:

1. **Liveness Probe**:
   - `GET /health/liveness`
   - Returns: `{"status": "alive"}`
   - Use: Detects if the process has deadlocked or crashed.

2. **Readiness Probe**:
   - `GET /health/readiness`
   - Returns: `{"status": "ready", "database": "healthy", "redis": "healthy"}`
   - Use: Verifies database and cache connections before admitting incoming traffic.

3. **Public API Health Endpoint**:
   - `GET /api/v1/health`
   - Returns: `{"status": "healthy", "version": "1.0.0", "timestamp": "...", "database": "connected", "redis": "connected"}`
   - Use: Tested by the Vercel frontend client to verify backend connectivity.

---

## 5. Reverse Proxy & Header Forwarding

In production cloud environments, incoming TLS is terminated by a reverse proxy or load balancer (Cloudflare, AWS ALB, Render Edge Router).

The Uvicorn container command is configured with:
```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
```

This guarantees:
- `X-Forwarded-Proto` (`https`) is respected, allowing Secure cookies to be delivered correctly.
- `X-Forwarded-For` captures actual client IP addresses for audit logging and rate limiting.
