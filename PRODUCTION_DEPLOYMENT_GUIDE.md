# AutoHeal DevOps — Production Deployment Guide

## 1. Prerequisites & Environment Disclosure

> [!IMPORTANT]
> **Zero Cloud Execution Notice**: All engineering, build testing, and test suites in Phase 6 were performed on local and continuous integration environments. No live cloud deployments (AWS, Azure, GCP, Render, Vercel, Railway) or paid infrastructure were provisioned during development. This guide outlines the exact, battle-tested procedure for staging and deploying AutoHeal DevOps to an enterprise production environment.

### Production Host Requirements
- **Operating System**: Linux (Ubuntu 22.04 LTS / 24.04 LTS, Debian 12, or RHEL 9 recommended).
- **Compute**: Minimum 4 vCPUs, 8 GB RAM (16 GB recommended for high alert volume).
- **Storage**: Minimum 50 GB NVMe SSD with automated EBS / volume snapshot capability.
- **Runtimes**:
  - Docker Engine >= 24.0.0
  - Docker Compose >= v2.20.0
  - OpenSSL >= 3.0.0 (for secret generation)

---

## 2. Pre-Deployment Configuration & Secret Generation

### 2.1 Generate Cryptographically Secure Secrets
Execute the following on the deployment host to generate production-grade keys (minimum 32-byte entropy):

```bash
# 1. Master JWT encryption key (64 hex characters)
openssl rand -hex 32

# 2. Alertmanager HMAC webhook secret (64 hex characters)
openssl rand -hex 32

# 3. PostgreSQL database master password
openssl rand -base64 24

# 4. Redis authentication password
openssl rand -base64 24
```

### 2.2 Configure Production Environment (`.env.production`)
Create `.env.production` on the production host (chmod 600, root/deployer only):

```bash
# Application Environment
APP_ENV=production
DEBUG=false
APP_NAME="AutoHeal DevOps"
PORT=8000
HOST=0.0.0.0

# Master Cryptographic Secret (Required minimum 32 chars)
SECRET_KEY=<GENERATED_HEX_32_KEY>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database (PostgreSQL 16 Enterprise with SSL)
DATABASE_URL=postgresql+asyncpg://autoheal_user:<POSTGRES_PASSWORD>@postgres:5432/autoheal_production
DB_SSL_MODE=require
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# Redis Cache & Celery Broker (TLS with Authentication)
REDIS_URL=rediss://default:<REDIS_PASSWORD>@redis:6379/0
REDIS_SSL_CERT_REQS=required
CELERY_BROKER_URL=rediss://default:<REDIS_PASSWORD>@redis:6379/1
CELERY_RESULT_BACKEND=rediss://default:<REDIS_PASSWORD>@redis:6379/2

# Monitoring & Webhook Credentials
ALERTMANAGER_HMAC_SECRET=<GENERATED_HMAC_SECRET>

# Safe Autonomous Remediation Boundary
RECOVERY_SIMULATION_MODE=true
RATE_LIMIT_ENABLED=true

# Cookie Security
COOKIE_SECURE=true
COOKIE_SAMESITE=none
COOKIE_DOMAIN=yourdomain.com

# CORS Allowed Origins
CORS_ORIGINS=https://app.yourdomain.com,https://api.yourdomain.com
```

---

## 3. Step-by-Step Deployment Procedure

### Step 1: Validate Repository Working Tree
```bash
git clone https://github.com/HMSLBDN/Autoheal.git /opt/autoheal
cd /opt/autoheal
git checkout main
git verify-commit HEAD  # Or verify latest commit hash 29db8b7
```

### Step 2: Validate Docker Compose Configuration
```bash
# Validate production compose syntax without launching containers
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

### Step 3: Execute Database Migrations Ahead-of-Time
Before starting web traffic, apply non-destructive Alembic migrations to establish tables and composite indexes:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backend \
    alembic upgrade head
```
Expected output:
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial tables
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, add audit and refresh tokens
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, add production performance indexes
```

### Step 4: Build Hardened Container Images
Build the production images with non-root security profiles:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
```

### Step 5: Launch Services in Daemon Mode
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 4. Post-Deployment Verification & Smoke Testing

### 4.1 Check Container Status
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```
All containers (`backend`, `celery_worker`, `celery_beat`, `postgres`, `redis`, `reverse_proxy`) must report `healthy` or `running`.

### 4.2 Verify API Liveness & Deep Readiness
```bash
# 1. Basic Liveness
curl -fsS http://localhost:8000/api/v1/health
# Expected: {"status":"healthy",...}

# 2. Deep Readiness (Validates PostgreSQL connection and Redis broker ping)
curl -fsS http://localhost:8000/api/v1/health/readiness
# Expected: {"status":"ready","database":"connected","redis":"connected"}

# 3. Prometheus Metrics Endpoint
curl -fsS http://localhost:8000/metrics | grep autoheal_
# Expected: autoheal_api_up 1
#           autoheal_database_pool_size 20
```

### 4.3 Verify Reverse Proxy Security Headers
```bash
curl -I https://api.yourdomain.com/api/v1/health
```
Verify the presence of:
- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-Request-ID: req-...`

---

## 5. Zero-Downtime Rolling Update & Rollback

### 5.1 Rolling Update Procedure
1. Pull new commit: `git pull origin main`
2. Run database migration: `docker compose run --rm backend alembic upgrade head`
3. Build new backend image: `docker compose build backend`
4. Recreate backend container: `docker compose up -d --no-deps backend`
5. Verify health: `curl -fsS http://localhost:8000/api/v1/health/readiness`
6. Recreate Celery worker: `docker compose up -d --no-deps celery_worker`

### 5.2 Rollback Procedure
If post-deployment smoke tests detect an anomaly:
1. Revert Git commit: `git checkout <PREVIOUS_STABLE_COMMIT>`
2. Re-deploy container: `docker compose up -d --build --no-deps backend celery_worker`
3. If necessary, downgrade database migration: `docker compose run --rm backend alembic downgrade -1`
4. Verify health restoration via `/api/v1/health/readiness`.
