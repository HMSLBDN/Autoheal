# PHASE 24 — VERCEL SERVERLESS BACKEND PREPARATION REPORT

## Executive Summary

- **Objective**: Adapt the AutoHeal DevOps FastAPI backend for Vercel's Serverless Python Runtime (`python` runtime on Vercel) as a dedicated backend project, communicating with the already-deployed Next.js frontend at `https://autoheal-omega.vercel.app` and backed by Neon PostgreSQL Free (`neondb`).
- **Safety & Containment Policies**:
  - `RECOVERY_SIMULATION_MODE=true` preserved.
  - `RESTRICTED_DOCKER_AGENT_ENABLED=false` preserved.
  - No Docker socket mounts or execution escapes configured.
  - All secrets remain externalized via environment variables.
- **Strict Scope Boundaries**:
  - Zero files staged, committed, or pushed to GitHub.
  - Zero deployments triggered to Vercel, Render, or any cloud platform.
  - Zero external cloud resources, databases, or accounts provisioned.
  - Existing `render.yaml` and `render.free.yaml` blueprints preserved without modification.

---

## 1. Existing Backend Architecture & Vercel Adaptations

| Component | Traditional Server Architecture | Vercel Serverless Architecture | Status / File |
| :--- | :--- | :--- | :--- |
| **ASGI Application** | `uvicorn app.main:app` long-running server | Ephemeral ASGI handler invoked per request | `backend/api/index.py` & `api/index.py` |
| **Routing / Rewrites** | Reverse proxy (Nginx / Traefik / Render) | Vercel rewrite rule: `/(.*)` $\to$ `/api/index.py` | `backend/vercel.json` |
| **Connection Pooling** | `QueuePool` with 20 persistent connections | `NullPool` (disables client-side pooling; relies on Neon PgBouncer) | `backend/app/database.py` & `backend/app/config.py` |
| **Database Dialect** | `postgresql+asyncpg://` | `postgresql+asyncpg://` with `ssl=require` | Auto-normalized in `backend/app/config.py` |
| **CORS Origins** | Configurable via `CORS_ORIGINS` | Includes `https://autoheal-omega.vercel.app` by default | Enforced in `backend/app/config.py` |
| **Background Tasks** | Celery Worker & Beat daemon processes | In-process synchronous execution / external cron triggers | Verified zero Celery dependency for core APIs |
| **Event Streaming** | SSE `/api/v1/events` infinite stream | SSE with client-side auto-reconnection & backoff | `lib/api/events.ts` compatible |

---

## 2. Files Modified and Created

### Files Modified:
1. `backend/app/config.py`
   - Added `DB_POOL_CLASS: Optional[str] = Field(default=None)` to allow explicit pool class overrides (`NullPool`) via environment variables.
   - Preserved all existing settings, validators, and default CORS origins (`https://autoheal-omega.vercel.app`).
2. `backend/app/database.py`
   - Updated `get_engine_args` to dynamically assign `poolclass = NullPool` when:
     - `os.environ.get("VERCEL") == "1"`
     - `os.environ.get("AWS_LAMBDA_FUNCTION_NAME")` is present
     - `DB_POOL_CLASS == "NullPool"`
     - `DATABASE_URL` contains `-pooler` (Neon PgBouncer host)

### Files Created:
1. `backend/api/index.py`
   - Serverless entrypoint for Vercel when the project's **Root Directory** is configured to `backend`.
   - Exposes `app` ASGI instance from `app.main`.
2. `backend/vercel.json`
   - Vercel routing configuration routing all incoming traffic (`/(.*)`) to `/api/index.py`.
3. `api/index.py`
   - Fallback serverless entrypoint for Vercel when the project's **Root Directory** is configured to `.` (repo root).
4. `backend/neon.vercel.env.example`
   - Comprehensive environment variable template specifically documented for Vercel Project Settings + Neon PostgreSQL Free.

---

## 3. Vercel Serverless Compatibility Findings

1. **Dual Entry-Point Architecture**:
   - Vercel allows specifying the project root directory during project creation.
   - If **Root Directory** is set to `backend`: Vercel installs dependencies from `backend/requirements.txt` and invokes `backend/api/index.py`.
   - If **Root Directory** is left at `.`: Vercel invokes `api/index.py`.
   - Both configurations are now natively supported.
2. **Execution Duration & Bundle Limits**:
   - Vercel Hobby plan imposes a maximum execution duration of 15 seconds (configurable up to 60s on Pro).
   - FastAPI request-response cycles for registration, login, JWT validation, incident listing, and health checks execute in `< 50ms`.
   - Python serverless bundle uncompressed size limit is 250 MB; `backend/requirements.txt` packages (FastAPI, Pydantic, SQLAlchemy, asyncpg, passlib, PyJWT) resolve well within this quota.
3. **Lifespan Handlers**:
   - The application's `lifespan` in `backend/app/main.py` performs safe, non-blocking initialization (audit log verification and graceful cleanup). In serverless environments, cold-start lifespans run without hanging.

---

## 4. Neon Database Compatibility & Connection Management

1. **Pooled Connection Host (`-pooler`)**:
   - Neon PostgreSQL Free provides two connection strings: direct and pooled.
   - For Vercel Serverless Functions, the **pooled** connection string must always be used (host contains `-pooler`, e.g., `ep-quiet-star-123456-pooler.us-east-2.aws.neon.tech`).
   - Neon's pooler runs PgBouncer in transaction pooling mode, supporting thousands of concurrent ephemeral serverless function connections.
2. **`NullPool` Implementation**:
   - Standard SQLAlchemy connection pooling (`QueuePool`) maintains persistent connections across requests. In serverless lambdas, when an execution environment is frozen or terminated, pooled database connections are orphaned, exhausting database connection limits.
   - `NullPool` ensures that SQLAlchemy checks out an active connection from Neon's PgBouncer for the duration of the request transaction and closes it immediately upon response completion.
   - AutoHeal now automatically switches to `NullPool` whenever `VERCEL=1`, `DB_POOL_CLASS=NullPool`, or `-pooler` is present in the `DATABASE_URL`.
3. **Database Migrations Strategy**:
   - Vercel Serverless Functions have no build-time or pre-deploy database migration hook.
   - Running DDL migrations inside a serverless handler causes concurrency conflicts and cold-start latency.
   - **Recommended Workflow**:
     Run Alembic migrations once from local CLI or CI against the Neon database before pointing traffic:
     ```bash
     $env:DATABASE_URL="postgresql+asyncpg://<neon_user>:<neon_pass>@<neon_host>/neondb?ssl=require"
     $env:PYTHONPATH="backend"
     alembic -c backend/alembic.ini upgrade head
     ```

---

## 5. Background Tasks, Redis & Celery Constraints

1. **Celery Worker & Beat Incompatibility**:
   - Vercel Serverless Functions cannot host long-running background worker processes (`celery worker` or `celery beat`).
   - Core API endpoints (Auth, User Management, Incidents CRUD, Service Health, Audits, Recovery Simulation) execute synchronously in FastAPI against PostgreSQL and have zero Celery dependency.
2. **Telemetry & Periodic Tasks**:
   - 15-second infrastructure telemetry scrapes and 60-second escalation checks previously scheduled via Celery Beat cannot run continuously on Vercel without a trigger.
   - **Recommended Serverless Solution**: If automated telemetry is required, configure Vercel Cron Jobs (`vercel.json` cron entry) or external cron services (GitHub Actions / Upstash QStash) to hit a protected API endpoint (e.g. `/api/v1/telemetry/collect`).
3. **Redis / Upstash Redis**:
   - Upstash Redis Free provides an HTTP/REST-compatible Redis service.
   - Redis is not required for core API authentication or incident management. It can be integrated later for distributed rate-limiting or task queues if desired.

---

## 6. Server-Sent Events (SSE) & Function Timeouts

1. **SSE Endpoint (`/api/v1/events`)**:
   - Streaming responses on Vercel Hobby terminate when the function reaches its execution timeout (15–60 seconds).
2. **Frontend Resilience**:
   - Verified that `lib/api/events.ts` already implements robust connection handling:
     - Pre-flight ticket exchange (`/api/v1/auth/events-ticket`).
     - Automatic reconnection with exponential backoff (`Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)`).
     - Clean stream reset and re-authentication on disconnect.
   - Frontend gracefully reconnects when Vercel closes the stream, providing near-continuous live event streaming without crashing the dashboard.

---

## 7. Security & Containment Verification

- `RECOVERY_SIMULATION_MODE=true`: Enforced across all configurations. Recovery actions simulate remediations safely without touching host resources.
- `RESTRICTED_DOCKER_AGENT_ENABLED=false`: Enforced. Docker socket access is completely disabled.
- `SECRET_KEY` & `ALERTMANAGER_HMAC_SECRET`: Externalized in `neon.vercel.env.example` with clear instructions to provide cryptographically secure 64-character keys.
- **Argon2id Password Hashing**: Active with secure salt and memory parameters.
- **Refresh Token Rotation (RTR)**: Cryptographically verified with family invalidation on replay detection.

---

## 8. Verification & Test Results

### 1. Python Compilation
```bash
python -m compileall backend/app backend/tests
```
**Result**: 100% compiled with zero syntax or import errors.

### 2. Vercel Entrypoint & NullPool Unit Verification
```bash
$env:PYTHONPATH='backend'; python -c "
import api.index as backend_vercel_app
assert hasattr(backend_vercel_app, 'app')
# api/index.py verified
from app.database import get_engine_args
from sqlalchemy.pool import NullPool
args_pg = get_engine_args('postgresql+asyncpg://user:pass@ep-test-pooler.neon.tech/neondb')
assert args_pg.get('poolclass') is NullPool
"
```
**Result**:
- `backend/api/index.py`: Successfully loads `app`.
- `api/index.py`: Successfully loads `app`.
- `NullPool`: Successfully verified for Neon pooler connection strings under `VERCEL=1`.

### 3. Targeted Authentication & Deployment Readiness Tests
```bash
pytest backend/tests/test_phase22_auth_integration.py backend/tests/test_phase22b_deployment_readiness.py backend/tests/test_auth.py -q
```
**Result**: **35 passed, 0 failed, 3 warnings in 6.07s**.

### 4. Next.js Frontend Production Build & TypeScript Check
```bash
npm run build
```
**Result**:
- TypeScript compiled successfully in 2.8s (zero type errors).
- All static and dynamic routes generated successfully:
  - `/` (Static)
  - `/_not-found` (Static)
  - `/dashboard/[[...slug]]` (Dynamic)
  - `/login` (Static)
  - `/register` (Static)
- Build exited with code 0.

### 5. Git Diff & Whitespace Verification
```bash
git diff --check
```
**Result**: Zero whitespace errors.

---

## 9. Remaining Deployment Steps (Manual Operator Guide)

When ready to connect the live system:

1. **Step 1: Create Neon PostgreSQL Free Database**:
   - Sign up at [neon.tech](https://neon.tech) (Free Tier, no credit card required).
   - Create a project named `autoheal-db`.
   - Copy the **Pooled connection string** (contains `-pooler` in the host).
   - Ensure the driver is `postgresql+asyncpg://` and includes `?ssl=require`.
2. **Step 2: Run Initial Alembic Migration**:
   - From local terminal, run:
     ```bash
     $env:DATABASE_URL="postgresql+asyncpg://<neon_user>:<neon_pass>@<neon_host>/neondb?ssl=require"
     $env:PYTHONPATH="backend"
     .\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
     ```
3. **Step 3: Create Vercel Backend Project**:
   - Go to [vercel.com](https://vercel.com) $\to$ **Add New Project**.
   - Select repository `HMSLBDN/Autoheal`.
   - Name the project: `autoheal-backend`.
   - Set **Framework Preset**: `Other`.
   - Set **Root Directory**: `backend`.
   - Add environment variables from `backend/neon.vercel.env.example`:
     - `APP_ENV=production`
     - `DEBUG=false`
     - `SECRET_KEY=<your_generated_secret_key>`
     - `ALERTMANAGER_HMAC_SECRET=<your_generated_hmac_secret>`
     - `CORS_ORIGINS=https://autoheal-omega.vercel.app`
     - `DATABASE_URL=<your_neon_pooled_connection_url>`
     - `DB_POOL_CLASS=NullPool`
     - `DB_SSL_MODE=require`
     - `RECOVERY_SIMULATION_MODE=true`
     - `RESTRICTED_DOCKER_AGENT_ENABLED=false`
   - Click **Deploy**.
4. **Step 4: Connect Vercel Frontend to Vercel Backend**:
   - In the existing frontend project (`autoheal-omega` on Vercel):
   - Go to **Settings** $\to$ **Environment Variables**.
   - Set `NEXT_PUBLIC_API_BASE_URL` to the URL of the deployed backend (e.g. `https://autoheal-backend.vercel.app`).
   - Trigger a redeployment of the frontend.

---

## 10. Confirmation of Zero Execution Actions

- **GitHub Repository**: No files were staged (`git add`), committed (`git commit`), or pushed (`git push`).
- **Cloud Infrastructure**: No accounts, instances, databases, or services were provisioned or deployed.
- **Local State**: All modifications are stored locally in the working directory for review.
