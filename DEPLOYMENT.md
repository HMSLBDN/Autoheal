# AutoHeal DevOps — Production Public Hosting & Deployment Guide

This guide details the procedure for deploying the **AutoHeal DevOps FastAPI backend, PostgreSQL 16 database, and Redis 7 instance** to secure, beginner-friendly managed cloud hosting, and connecting the live **Vercel frontend** (`https://autoheal-omega.vercel.app`).

---

## 1. System Architecture

```text
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│     Vercel Frontend (Live)      │                 │     Managed Container Cloud     │
│ https://autoheal-omega.vercel.app│                 │     (Render / Railway / AWS)    │
│                                 │                 │                                 │
│  • Next.js App Router (16.4.6)  │  HTTPS Request  │  • FastAPI Backend (Uvicorn)    │
│  • React 19 UI                  ├────────────────►│  • Port: dynamic ($PORT)        │
│  • Bearer Token Authentication  │  (with cookies) │  • Non-root container (autoheal)│
│  • HttpOnly Cookie RTR Session  │                 │  • Health Probe: /api/v1/health │
└─────────────────────────────────┘                 └───────────────┬─────────────────┘
                                                                    │ Private Network
                                                    ┌───────────────┴─────────────────┐
                                                    │                                 │
                                                    │  • Managed PostgreSQL 16        │
                                                    │    (Persistent storage)         │
                                                    │  • Managed Redis 7              │
                                                    │    (Celery broker & cache)      │
                                                    │  • Celery Worker (Async jobs)   │
                                                    └─────────────────────────────────┘
```

---

## 2. Option A: One-Click Render Blueprint Deployment (`render.yaml`)

The repository includes a production-ready declarative blueprint ([`render.yaml`](./render.yaml)) that automatically provisions all required services in a secure, isolated private network.

### Step 1 — Create the Blueprint on Render
1. Sign in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** $\to$ **Blueprint**.
3. Select and connect your repository: `https://github.com/HMSLBDN/Autoheal.git` (branch: `main`).
4. Render will detect `render.yaml` and display the resources to be created:
   - **`autoheal-backend`**: Docker Web Service running FastAPI.
   - **`autoheal-celery-worker`**: Docker Background Worker for async self-healing tasks.
   - **`autoheal-db`**: Managed PostgreSQL 16 database with persistent storage.
   - **`autoheal-redis`**: Managed Redis 7 instance for queues and caching.
5. Click **Apply**. Render will automatically provision the database and Redis, generate secure secrets (`SECRET_KEY`, `ALERTMANAGER_HMAC_SECRET`), and build the Docker images.

### Step 2 — Run Database Migrations & Initial Seeding
Once `autoheal-backend` is deployed:
1. In the Render Dashboard, open the **`autoheal-backend`** service.
2. Navigate to the **Shell** tab (or connect via Render CLI / SSH).
3. Execute the database schema migrations:
   ```bash
   alembic upgrade head
   ```
4. Seed baseline roles, default organizations, and services:
   ```bash
   python seed.py
   ```
5. Verify the health probe:
   ```bash
   curl -i http://127.0.0.1:$PORT/api/v1/health
   ```

### Step 3 — Copy the Public Backend URL
In the Render dashboard for `autoheal-backend`, copy the generated public HTTPS URL:
```text
https://autoheal-backend-xxxx.onrender.com
```

---

## 3. Option B: Manual Container Deployment (Railway, Fly.io, Cloud Run, AWS)

If deploying to another container hosting platform, configure the following services:

### 1. PostgreSQL 16 (Managed)
- Provision a PostgreSQL 16 database with persistent volume storage.
- Ensure the database is inside a private network or accessible only via authorized IP allowlists.
- Copy the connection URL (`postgres://user:pass@host:5432/dbname`). The application automatically normalizes this to `postgresql+asyncpg://`.

### 2. Redis 7 (Managed)
- Provision a Redis 7 instance.
- Enable `requirepass` authentication.
- Copy the connection URI (`redis://:password@host:6379/0` or `rediss://...` for TLS).

### 3. FastAPI Web Service (`backend/Dockerfile`)
- **Docker Context:** `./backend`
- **Dockerfile Path:** `./backend/Dockerfile`
- **Exposed Port:** `$PORT` (assigned by the platform, defaults to `8000`)
- **Health Check Path:** `/api/v1/health`
- **Environment Variables:**
  ```ini
  APP_ENV=production
  DEBUG=False
  PORT=8000
  HOST=0.0.0.0
  SECRET_KEY=<generate_random_64_character_string>
  CORS_ORIGINS=https://autoheal-omega.vercel.app,https://autoheal-devops.vercel.app
  DATABASE_URL=postgresql+asyncpg://<db_user>:<db_password>@<db_host>:5432/<db_name>
  REDIS_URL=redis://:<redis_password>@<redis_host>:6379/0
  ALERTMANAGER_HMAC_SECRET=<generate_random_32_character_string>
  ```
- **Post-Deploy Migration Command:**
  ```bash
  alembic upgrade head && python seed.py
  ```

### 4. Celery Worker (`backend/Dockerfile.celery_worker`)
- **Docker Context:** `./backend`
- **Dockerfile Path:** `./backend/Dockerfile.celery_worker`
- **Environment Variables:** Provide the identical `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `APP_ENV=production`.

---

## 4. Frontend Vercel Configuration

After obtaining your public backend HTTPS URL (e.g., `https://autoheal-backend-xxxx.onrender.com`):

### Step 1 — Add Environment Variables in Vercel
1. Navigate to your project on the [Vercel Dashboard](https://vercel.com).
2. Go to **Settings** $\to$ **Environment Variables**.
3. Add the following variables:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://autoheal-backend-xxxx.onrender.com` | Public backend URL **(no trailing slash, no `/api/v1`)**. |
| `NEXT_PUBLIC_DEMO_MODE` | `false` | Explicitly disables demo/preview mode in production. |

### Step 2 — Redeploy the Frontend
Because Next.js embeds `NEXT_PUBLIC_*` variables during static compilation:
1. In Vercel, go to the **Deployments** tab.
2. Click the three dots (`...`) on the latest deployment and select **Redeploy**.
3. Wait for the build to complete (typically 30–60 seconds).

---

## 5. Security & Verification Checklist

Once both frontend and backend are deployed and connected:

1. **Visit the Login Page:**
   - Open `https://autoheal-omega.vercel.app/login`.
   - The warning banner will now display:
     `Connected to AutoHeal API. Secured with Argon2id hashing and JWT access tokens.`
2. **Test User Registration:**
   - Click "Create an account" (`/register`).
   - Register a new account (`engineer@example.com`).
   - The user is created in PostgreSQL with Argon2id hashing and scoped to the organization.
3. **Test Login & Protected Dashboard:**
   - Sign in with the registered credentials.
   - The browser receives an access token and an HttpOnly `refresh_token` cookie.
   - The application routes to `/dashboard` and loads live cluster data via `GET /api/v1/auth/me`.
4. **Test Session Persistence:**
   - Refresh the browser page (`F5`).
   - The session remains active; `performTokenRefresh()` rotates the token automatically if the 15-minute access token expires.
5. **Test Sign Out:**
   - Click the user profile icon and select **Sign out**.
   - The backend revokes the refresh-token family in PostgreSQL, clears the browser cookie, and routes to `/login`.
