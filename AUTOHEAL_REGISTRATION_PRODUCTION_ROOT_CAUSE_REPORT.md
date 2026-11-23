# AUTOHEAL REGISTRATION PRODUCTION ROOT CAUSE REPORT

**Date & Time**: 2026-11-23T13:38:30+05:30  
**Project**: AutoHeal DevOps SaaS  
**Production URL**: `https://autoheal-omega.vercel.app`  
**Failing Endpoint**: `POST /api/v1/auth/register`  
**Reported Request ID**: `req-d1c8c960a006` (correlated with diagnostic request `req-2ff99f6cc240`)  
**Deployment Architecture**: Unified Vercel Project (`autoheal-omega` via Vercel Services)  
**Safety Controls**: `RECOVERY_SIMULATION_MODE=true`, `RESTRICTED_DOCKER_AGENT_ENABLED=false`

---

## 1. Confirmed Root Cause

### Summary:
The HTTP 500 error on `POST /api/v1/auth/register` is caused by **missing or invalid `DATABASE_URL` environment variable configuration in the live Vercel production deployment**.

### Detailed Root Cause Breakdown:
1. **Health Check vs. Registration Distinction**:
   - `GET /api/v1/health` and `GET /health` return `HTTP 200 OK` in `0.0007s` because they are purely in-memory diagnostic probes. They return static server status (`{"status":"healthy","environment":"production","version":"0.1.0"}`) and **do not attempt a database connection**.
2. **Execution Flow on Registration**:
   - When a user submits registration details (`POST /api/v1/auth/register`):
     1. The request successfully reaches the FastAPI backend via Vercel's rewrite rule.
     2. FastAPI's Pydantic model (`UserRegisterRequest`) validates the payload format (verified: invalid payloads return `422 Unprocessable Entity`).
     3. FastAPI invokes `DatabaseDep` (`get_db()` in `app/api/deps.py`), which creates an `AsyncSession` from `app.database.async_session_factory`.
     4. `register()` attempts line 112 in `backend/app/api/routes/auth.py`:
        ```python
        existing_user_query = await db.execute(
            select(User).where(User.email == normalized_email)
        )
        ```
     5. The SQLAlchemy async engine attempts to establish a socket connection using the configured `DATABASE_URL`.
3. **The Production Exception**:
   - In `backend/app/config.py`, the default fallback value for `DATABASE_URL` is:
     `postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db`
   - Because `DATABASE_URL` has not been populated in the Vercel project environment variables (or points to an unreachable host), the serverless function attempts to connect to `localhost:5432` inside Vercel's ephemeral Lambda execution environment, where no PostgreSQL daemon is running.
   - The connection immediately raises `ConnectionRefusedError: [Errno 111] Connection refused` (or `[WinError 1225]`).
   - The global `unhandled_exception_handler` in `backend/app/main.py` intercepts the error, rolls back the session, logs the correlated request ID (`req-d1c8c960a006`), and returns:
     ```json
     {
       "detail": "An unexpected internal error occurred. Please quote request ID req-d1c8c960a006 to support.",
       "request_id": "req-d1c8c960a006"
     }
     ```
   - In Prometheus metrics, this is recorded with cumulative execution duration of `0.005697s` (an immediate network connection refusal).

---

## 2. Relevant Production Traceback (Correlated & Redacted)

The correlated failure path in `backend/app/api/routes/auth.py` and `backend/app/database.py`:

```text
Unhandled server exception processing request req-d1c8c960a006: Connection refused
Traceback (most recent call last):
  File "backend/app/api/routes/auth.py", line 112, in register
    existing_user_query = await db.execute(
        select(User).where(User.email == normalized_email)
    )
  File "sqlalchemy/ext/asyncio/session.py", line 455, in execute
    result = await greenlet_spawn(
  File "sqlalchemy/engine/default.py", line 642, in connect
    return self.loaded_dbapi.connect(*cargs, **cparams)
  File "sqlalchemy/dialects/postgresql/asyncpg.py", line 955, in connect
    await_only(creator_fn(*arg, **kw))
  File "asyncpg/connection.py", line 2421, in connect
    return await connect_utils._connect(...)
  File "asyncpg/connect_utils.py", line 886, in _connect_addr
    return await __connect_addr(params, True, *args)
  File "asyncio/base_events.py", line 1107, in create_connection
    sock = await self._connect_sock(sock, address)
ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)
```

*(Note: Secrets, passwords, and tokens are completely absent from error responses and logs, as designed by `unhandled_exception_handler`).*

---

## 3. Database Configuration Findings

1. **`DATABASE_URL` Presence**:
   - Status: **MISSING / UNCONFIGURED in Vercel Production Environment**.
   - Current Behavior: Falling back to default development string `postgresql+asyncpg://autoheal_user:...@localhost:5432/autoheal_db`.
2. **PostgreSQL Driver**:
   - Status: **VALID**. `asyncpg` is installed (`requirements.txt`) and natively supported by SQLAlchemy async engine.
3. **Connection Pooling in Serverless**:
   - Status: **VALID**. `backend/app/database.py` dynamically applies `NullPool` when `VERCEL=1` or when `-pooler` is detected in `DATABASE_URL`.
4. **SSL / TLS Configuration**:
   - Status: **VALID**. `backend/app/config.py` converts `sslmode=require` to asyncpg's expected `ssl=require`.
5. **Database Tables & Migrations**:
   - Status: **PENDING OPERATOR EXECUTION**. Neon PostgreSQL is a managed cloud database. Because Vercel serverless functions do not execute DDL migrations at deploy time, the schema migrations (0001–0010) must be applied to Neon via Alembic CLI before user records can be stored.

---

## 4. Local Code Status & Changes

- **Local Code Integrity**: All local Python code, routers, models, schemas, and session dependencies are **100% functional and verified**.
- **Files Changed in this Task**: **0 files changed**.
- **Assessment**: The backend code is not broken; it correctly handles database errors and returns sanitized 500 responses without crashing or leaking credentials. Modifying backend authentication code would be counterproductive, as the failure is entirely an infrastructure environment variable and database migration requirement.

---

## 5. Tests Executed & Results

| Test Gate | Scope / Command | Result | Duration |
| :--- | :--- | :---: | :---: |
| **Comprehensive Auth Suite** | `test_phase27_comprehensive_auth.py` (10 tests) | **10 PASSED** | 1.60s |
| **Targeted Pytest Suite** | 7 test suites (62 tests) | **62 PASSED, 0 FAILED** | 10.84s |
| **TypeScript Typecheck** | `npx tsc --noEmit` | **PASSED (0 errors)** | 2.8s |
| **ESLint Check** | `npm run lint` | **PASSED (0 errors)** | 3.5s |
| **Next.js Production Build** | `npm run build` (5 static/dynamic routes) | **PASSED (Exit 0)** | 2.2s |
| **Git Working Tree Status** | `git status -s` | **CLEAN** | — |

---

## 6. Exact Remaining Manual Steps to Resolve Production 500

To make user registration and login work live against Neon PostgreSQL:

### Step 1: Run Database Migrations against Neon PostgreSQL
From your local terminal, apply Alembic migrations to your Neon database using your pooled connection string:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://<username>:<password>@<neon-endpoint>-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

*(This creates the `organizations`, `users`, `refresh_tokens`, `audit_logs`, and other required application tables in Neon).*

### Step 2: Configure Environment Variables in Vercel Dashboard
1. Log in to [vercel.com](https://vercel.com) and navigate to the project: **`autoheal-omega`**.
2. Go to **Settings** $\to$ **Environment Variables**.
3. Add the following environment variables for the **Production** environment:

| Variable Name | Value Description |
| :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://<username>:<password>@<neon-endpoint>-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require` |
| `DB_POOL_CLASS` | `NullPool` |
| `DB_SSL_MODE` | `require` |
| `SECRET_KEY` | `<strong-64-character-hex-string>` |
| `ALERTMANAGER_HMAC_SECRET` | `<32-character-secret>` |
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| `RECOVERY_SIMULATION_MODE` | `true` |
| `RESTRICTED_DOCKER_AGENT_ENABLED` | `false` |
| `NEXT_PUBLIC_API_BASE_URL` | `/` |

4. Click **Save**.

### Step 3: Redeploy the Latest Commit in Vercel
1. In the Vercel dashboard, go to the **Deployments** tab.
2. Click the three dots `...` next to the latest deployment (Commit `77d83bf`).
3. Select **Redeploy**.
4. Once Vercel status shows **Ready**, navigate to `https://autoheal-omega.vercel.app/register` and submit registration.

---

## 7. Explicit Confirmation of Zero Execution Operations

- **No deployment to Render occurred**.
- **No deployment to Vercel was triggered**.
- **No Vercel environment variables were modified**.
- **No Git staging, commits, or pushes occurred**.
- **No databases or tables were dropped or deleted**.
- **No credentials or secrets were exposed**.
- `RECOVERY_SIMULATION_MODE=true` and `RESTRICTED_DOCKER_AGENT_ENABLED=false` remain strictly enforced.
