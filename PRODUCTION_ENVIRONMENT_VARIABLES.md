# AutoHeal DevOps — Production Environment Variables Reference

This document provides the definitive specification of all environment variables required across the frontend, FastAPI backend, Celery worker, and periodic scheduler.

---

## 1. Frontend Environment Variables (Vercel Project Dashboard)

Configure these variables under **Vercel Dashboard** $\to$ **Project Settings** $\to$ **Environment Variables**.

| Variable Name | Required | Example Production Value | Purpose & Architectural Behavior |
| :--- | :---: | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | **Yes** | `https://autoheal-backend-xxxx.onrender.com` | Base public URL of the deployed FastAPI backend. Must **NOT** have a trailing slash or `/api/v1`. Baked into client JavaScript bundle at build time. |
| `NEXT_PUBLIC_DEMO_MODE` | No | `false` | Explicitly disables demo preview fallbacks in production. When `false`, the UI never substitutes mock data. |

---

## 2. Backend Web API Service (`autoheal-backend`)

Configure these variables in your container hosting platform (Render, Railway, AWS ECS, Fly.io).

| Variable Name | Required | Supported Aliases | Default | Description |
| :--- | :---: | :--- | :--- | :--- |
| `APP_ENV` | **Yes** | `ENVIRONMENT` | `development` | Set strictly to `production`. Enables secure cookie attributes (`SameSite=None`, `Secure=True`), disables interactive `/docs`, enables request tracing. |
| `DEBUG` | **Yes** | None | `True` | Set strictly to `false` in production. Disables debug tracebacks and SQL query echoing. |
| `PORT` | Auto | None | `8000` | Injected dynamically by container hosting platforms (Render, Cloud Run, Railway). Backend binds dynamically via `${PORT:-8000}`. |
| `HOST` | No | None | `0.0.0.0` | Binds to all interfaces inside the container. |
| `SECRET_KEY` | **Yes** | `JWT_SECRET_KEY` | Dev Default *(Fails in prod!)* | Cryptographic master key for JWT signature generation (HS256). Must be high-entropy 64-char string (e.g. `openssl rand -hex 32`). |
| `DATABASE_URL` | **Yes** | None | Local URI | Connection URI for PostgreSQL 16. Automatically converts `postgres://` or `postgresql://` $\to$ `postgresql+asyncpg://` and translates `sslmode=require` $\to$ `ssl=require`. |
| `REDIS_URL` | **Yes** | `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Connection URI for Redis 7. Supports `redis://` or `rediss://` for TLS. Used for Celery broker, results, and session revocation. |
| `CORS_ORIGINS` | **Yes** | `ALLOWED_ORIGINS` | Permitted origins | Comma-separated list or JSON array of trusted frontend domains: `https://autoheal-omega.vercel.app,https://autoheal-devops.vercel.app`. |
| `ALERTMANAGER_HMAC_SECRET` | **Yes** | `ALERTMANAGER_WEBHOOK_SECRET` | Dev Secret | Shared secret key for verifying Prometheus/Alertmanager webhook HMAC signatures (`X-AutoHeal-Signature`). |
| `GEMINI_API_KEY` | Optional | None | None | Google AI Studio API key. Enables automated root-cause diagnosis via Gemini 1.5 Pro. |
| `AI_PROVIDER` | No | None | `none` | AI provider selector: `gemini`, `anthropic`, `openai`, or `none`. |
| `COOKIE_SECURE` | No | None | Auto (`True` in prod) | Forces HTTPS transmission on refresh token cookies. |
| `COOKIE_SAMESITE` | No | None | Auto (`none` in prod) | Allows cross-origin cookie transmission between Vercel and backend domains. |
| `COOKIE_DOMAIN` | No | None | `None` (Host-only) | When unset, cookie is strictly bound to backend domain, preventing cross-subdomain leakage. |

---

## 3. Celery Background Worker (`autoheal-celery-worker`)

| Variable Name | Required | Supported Aliases | Purpose |
| :--- | :---: | :--- | :--- |
| `APP_ENV` | **Yes** | `ENVIRONMENT` | `production` |
| `DATABASE_URL` | **Yes** | None | Identical to backend PostgreSQL URI. |
| `REDIS_URL` | **Yes** | `CELERY_BROKER_URL` | Identical to backend Redis URI. |
| `SECRET_KEY` | **Yes** | `JWT_SECRET_KEY` | Identical to backend secret key. |
| `GEMINI_API_KEY` | Optional | None | Powers asynchronous AI diagnostic worker tasks. |

---

## 4. Celery Beat Scheduler (`autoheal-celery-beat`)

| Variable Name | Required | Purpose |
| :--- | :---: | :--- |
| `APP_ENV` | **Yes** | `production` |
| `DATABASE_URL` | **Yes** | Identical to backend PostgreSQL URI. |
| `REDIS_URL` | **Yes** | Identical to backend Redis URI. |
| `SECRET_KEY` | **Yes** | Identical to backend secret key. |
