# PHASE 25 — VERCEL SERVICES INTEGRATION REPORT: UNIFIED NEXT.JS & FASTAPI DEPLOYMENT

**Date & Time**: 2026-11-23T12:14:30+05:30  
**Project**: AutoHeal DevOps SaaS  
**Target Vercel Project**: `autoheal-omega`  
**Shared Domain**: `https://autoheal-omega.vercel.app`  
**Repository**: `HMSLBDN/Autoheal` (Branch: `main`)  
**Database**: Neon PostgreSQL Free (Region: Singapore `ap-southeast-1`, pooled host with `-pooler`)

---

## 1. Executive Summary

This phase investigates and implements the **Vercel Services** monorepo architecture, enabling the Next.js frontend and FastAPI backend to deploy simultaneously within the single, existing Vercel project (`autoheal-omega`). Both services share the same root domain (`https://autoheal-omega.vercel.app`), eliminating cross-origin CORS latency, eliminating the need to maintain separate Vercel projects, and delivering an integrated full-stack deployment.

### Key Highlights:
1. **Zero Cloud Resources Created / Zero Dashboard Changes**: No Vercel projects, databases, or cloud modifications were executed.
2. **Zero Git Operations**: No staging (`git add`), commits (`git commit`), or pushes (`git push`) were performed.
3. **Safety Compliance**: `RECOVERY_SIMULATION_MODE=true` and `RESTRICTED_DOCKER_AGENT_ENABLED=false` remain strictly verified and active.
4. **Clean Routing**: Next.js handles all UI routes (`/`, `/login`, `/register`, `/dashboard/*`) while FastAPI handles dedicated backend routes (`/api/v1/*`, `/api/*`, `/health`, `/metrics`, `/docs`, `/openapi.json`) without route collisions.

---

## 2. Architecture: Before vs. After

### Before (Separate Projects Approach):
- **Frontend Project**: `autoheal-omega` on Vercel (`https://autoheal-omega.vercel.app`), root directory `.` (or empty).
- **Backend Project**: Proposed separate Vercel project (e.g. `autoheal-backend.vercel.app`), root directory `backend`.
- **Communication**: Cross-origin HTTPS requests requiring CORS headers, separate deployment pipelines, and cross-project environment variable synchronization.

```mermaid
flowchart TD
    User["User Browser"] -->|"UI Requests"| VercelFrontend["Vercel Project: autoheal-omega\n(Next.js)"]
    User -->|"CORS API Requests"| VercelBackend["Separate Vercel Project\n(FastAPI Serverless)"]
    VercelBackend -->|"Pooled Asyncpg"| NeonDB["Neon PostgreSQL (Singapore)\n-pooler.ap-southeast-1.neon.tech"]
```

### After (Unified Vercel Services Architecture):
- **Single Vercel Project**: `autoheal-omega` (`https://autoheal-omega.vercel.app`).
- **Services Configuration**: Root `vercel.json` defines two internal services:
  - `frontend`: Next.js application at root (`.`).
  - `backend`: FastAPI Python application at `backend/` with entrypoint `main:app`.
- **Top-Level Rewrites**: Vercel Edge Network inspects incoming requests and routes API paths directly to the backend service and all remaining paths to the Next.js frontend.
- **Communication**: Same-origin relative API requests (`/api/v1/...`). Zero CORS pre-flight latency for browser clients.

```mermaid
flowchart TD
    User["User Browser"] -->|"Single Domain: https://autoheal-omega.vercel.app"| Edge["Vercel Edge Router (vercel.json)"]
    Edge -->|"/api/v1/*, /health, /metrics"| BackendService["Vercel Service: backend\n(FastAPI in backend/main:app)"]
    Edge -->|"/(.*) UI Routes"| FrontendService["Vercel Service: frontend\n(Next.js at .)"]
    BackendService -->|"NullPool Connection"| NeonDB["Neon PostgreSQL Free (Singapore)\n-pooler.ap-southeast-1.aws.neon.tech"]
```

---

## 3. Exact Configuration Changes

### 1. Root `vercel.json` (Created)
Defined the multi-service architecture and public request routing:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "services": {
    "frontend": {
      "root": ".",
      "framework": "nextjs"
    },
    "backend": {
      "root": "backend/",
      "entrypoint": "main:app"
    }
  },
  "rewrites": [
    {
      "source": "/api/v1/:path*",
      "destination": {
        "service": "backend"
      }
    },
    {
      "source": "/api/:path*",
      "destination": {
        "service": "backend"
      }
    },
    {
      "source": "/health",
      "destination": {
        "service": "backend"
      }
    },
    {
      "source": "/metrics",
      "destination": {
        "service": "backend"
      }
    },
    {
      "source": "/docs",
      "destination": {
        "service": "backend"
      }
    },
    {
      "source": "/openapi.json",
      "destination": {
        "service": "backend"
      }
    },
    {
      "source": "/(.*)",
      "destination": {
        "service": "frontend"
      }
    }
  ]
}
```

### 2. Backend ASGI Entrypoint `backend/main.py` (Created)
Exposes the FastAPI instance `app` directly for Vercel's service discovery (`entrypoint: "main:app"`):

```python
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app

__all__ = ["app"]
```

### 3. Frontend Same-Origin API Client `lib/api/client.ts` (Updated)
Updated `isApiConfigured` and `API_BASE_URL` so that when Next.js is deployed alongside FastAPI under the same domain, an empty or unset `NEXT_PUBLIC_API_BASE_URL` automatically defaults to same-origin relative paths (`/api/v1/...`) in production rather than displaying "Backend not configured":

```typescript
export const isSameOriginDeployment =
  typeof window !== 'undefined' || process.env.NODE_ENV === 'production'

export const API_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || ''
)

export const isApiConfigured =
  API_BASE_URL.length > 0 ||
  process.env.NEXT_PUBLIC_API_BASE_URL === '' ||
  process.env.NEXT_PUBLIC_API_BASE_URL === '/' ||
  (process.env.NODE_ENV === 'production' && process.env.NEXT_PUBLIC_DEMO_MODE !== 'true')
```

---

## 4. Routing Design & Route Collision Analysis

1. **Frontend App Router Audit**:
   - Monitored directory `app/`: contains `dashboard/`, `login/`, `register/`, `page.tsx`, `layout.tsx`.
   - Audited directory `pages/api/` and `app/api/`: **Zero Next.js API route files exist**.
   - **Conclusion**: There are zero naming collisions between Next.js route handlers and FastAPI endpoints.
2. **Rewrite Ordering**:
   - Vercel evaluates top-level rewrites strictly top-to-bottom.
   - Specific prefixes (`/api/v1/*`, `/api/*`, `/health`, `/metrics`, `/docs`, `/openapi.json`) are matched first and sent to the `backend` service.
   - The catch-all pattern (`/(.*)`) is placed last, ensuring all user interface pages, Next.js static chunks (`/_next/static/*`), and assets route cleanly to Next.js.

---

## 5. Neon PostgreSQL (Singapore Region) & Connection Management

1. **Region & Host Specification**:
   - Neon Singapore region endpoints follow: `ep-xxxxxx-pooler.ap-southeast-1.aws.neon.tech`.
   - The connection string requires:
     `postgresql+asyncpg://<username>:<password>@<endpoint>-pooler.ap-southeast-1.aws.neon.tech/<database_name>?ssl=require`.
2. **NullPool Serverless Safety**:
   - `backend/app/database.py` contains automated detection:
     Whenever `VERCEL=1`, `DB_POOL_CLASS=NullPool`, or `-pooler` is detected in the `DATABASE_URL`, the engine uses `NullPool`.
   - Verified that both direct Neon URLs and pooled Singapore endpoints instantiate `NullPool`, preventing orphaned database connections across ephemeral serverless function lifecycles.
3. **Database Migrations Protocol**:
   - Vercel Services do not provide a container pre-deploy hook.
   - Migrations must be run once as a controlled operator step before routing production traffic:
     ```bash
     $env:DATABASE_URL="postgresql+asyncpg://<neon_user>:<neon_pass>@<neon_endpoint>-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
     $env:PYTHONPATH="backend"
     .\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
     ```

---

## 6. Vercel Services Beta & Billing Limitations

1. **Current Lifecycle Status**:
   - Vercel Services is currently in **Public Beta** across all plans (Hobby, Pro, Enterprise).
   - The modern `services` syntax replaces the deprecated `experimentalServices` schema (which is rejected for new deployments after July 2026).
2. **Plan & Billing Requirements**:
   - **Hobby ($0/mo)**: Supported with standard serverless execution limits (15-second max function timeout, 250 MB bundle limit).
   - **Pro ($20/mo per user)**: Recommended for production if extended function execution (up to 300s or beta 1800s) is required.
   - **Compute Granularity**: Functions in each service are billed under Fluid Compute metrics (active CPU runtime + memory).
   - **Service Invocations**: Rewrites to internal services count as internal service requests and do not incur external egress penalties between services.
3. **Background Worker & Celery Limitation**:
   - Vercel Services strictly handle routed workloads (inbound HTTP request-response).
   - Persistent worker processes (Celery Worker and Celery Beat daemon loops) cannot run inside Vercel Services.
   - Core API operations (authentication, incident management, service metrics queries, recovery simulation) execute synchronously in FastAPI against PostgreSQL and function at 100% capacity without Celery.
   - Background telemetry polling can be driven using **Vercel Cron Jobs** hitting an endpoint if automated scraping is needed.

---

## 7. Verification & Test Results

### 1. FastAPI Route Registration & ASGI Discovery
Verified that `backend/main.py` discovers all 130 FastAPI routes:
```
Total routes registered: 130
All core API routes verified:
- /health
- /metrics
- /api/v1/auth/login
- /api/v1/auth/register
- /api/v1/incidents
- /api/v1/services
- /api/v1/events/ticket
```

### 2. Neon Singapore Pooler & NullPool Test
```bash
$env:PYTHONPATH='backend'; python -c "
neon_sg_url = 'postgresql+asyncpg://autoheal_user:pass@ep-cool-butterfly-123456-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require'
args = get_engine_args(neon_sg_url)
assert args.get('poolclass') is NullPool
"
```
**Result**: **PASSED**. `NullPool` is dynamically enforced for Singapore pooled connections.

### 3. Backend Regression & Authentication Suite
```bash
pytest backend/tests/test_phase22_auth_integration.py backend/tests/test_phase22b_deployment_readiness.py backend/tests/test_auth.py -q
```
**Result**: **35 passed, 0 failed in 6.10s**.

### 4. Frontend Production Build & TypeScript Verification
```bash
npm run build
```
**Result**:
- `next build --webpack` completed successfully in 3.1s.
- TypeScript checked in 4.2s with **0 type errors**.
- All static and dynamic routes generated cleanly:
  - `/` (Static)
  - `/_not-found` (Static)
  - `/dashboard/[[...slug]]` (Dynamic)
  - `/login` (Static)
  - `/register` (Static)
- Exit code: 0.

### 5. Git Diff & Whitespace Audit
- `git diff --check` completed with **0 errors**.

---

## 8. Remaining Deployment Steps (Operator Checklist)

When ready to apply this deployment to Vercel:

1. **Step 1: Execute Database Migrations against Neon Singapore**:
   From your local terminal, apply Alembic migrations to the Neon Singapore database:
   ```powershell
   $env:DATABASE_URL="postgresql+asyncpg://<neon_user>:<neon_pass>@<endpoint>-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
   $env:PYTHONPATH="backend"
   .\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
   ```
2. **Step 2: Update Project Settings in Vercel (`autoheal-omega`)**:
   - Go to [vercel.com](https://vercel.com) $\to$ Select project `autoheal-omega`.
   - Verify **Root Directory** is set to `.` (the repository root).
   - In **Settings** $\to$ **Environment Variables**, configure:
     - `APP_ENV` = `production`
     - `DEBUG` = `false`
     - `SECRET_KEY` = `<strong_64_character_hex_key>`
     - `ALERTMANAGER_HMAC_SECRET` = `<strong_32_character_secret>`
     - `DATABASE_URL` = `postgresql+asyncpg://<neon_user>:<neon_pass>@<endpoint>-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require`
     - `DB_POOL_CLASS` = `NullPool`
     - `DB_SSL_MODE` = `require`
     - `RECOVERY_SIMULATION_MODE` = `true`
     - `RESTRICTED_DOCKER_AGENT_ENABLED` = `false`
     - `NEXT_PUBLIC_API_BASE_URL` = `/` (or leave empty to use same-origin relative URLs)
3. **Step 3: Trigger Deployment**:
   - Push authorized changes to `main` or trigger a redeployment in the Vercel dashboard.
   - Vercel will build both the Next.js `frontend` service and the FastAPI `backend` service atomically.
   - Test `https://autoheal-omega.vercel.app/health` and `https://autoheal-omega.vercel.app/login`.

---

## 9. Explicit Confirmation

- **No deployment triggered**: The live production environment was not altered.
- **No Git commits/pushes**: Working tree changes remain local pending user authorization.
- **No secrets committed**: Real database credentials and keys were not added to any tracked files.
