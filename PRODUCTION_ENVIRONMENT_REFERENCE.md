# AutoHeal DevOps — Production Environment Variable Reference

## 1. Overview & Security Rules

All configuration parameters in AutoHeal DevOps follow the Twelve-Factor App methodology. Values are ingested from environment variables and validated at application startup using Pydantic Settings (`pydantic-settings`).

### Strict Configuration Rules
1. **Never Commit Secrets**: Never commit `.env`, `.env.production`, or private key files to version control.
2. **Production Fail-Closed**: In `APP_ENV=production`, insecure or missing secrets (e.g. `SECRET_KEY`, `ALERTMANAGER_HMAC_SECRET`) immediately halt application startup with a descriptive configuration error.
3. **Frontend Variable Isolation**: The frontend only exposes `NEXT_PUBLIC_API_URL`. **No secrets, tokens, or webhook credentials are ever exposed to the client bundle.**

---

## 2. Exhaustive Environment Variable Catalog

### 2.1 Core Application & Server
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `APP_NAME` | string | `"AutoHeal DevOps API"` | `"AutoHeal DevOps"` | Public | Human-readable service name. |
| `APP_ENV` | enum | `"development"` | `"production"` | Public | Runtime environment: `development`, `staging`, `production`, `test`. |
| `DEBUG` | boolean | `true` | `false` | Public | Toggles verbose error handlers and interactive Swagger docs (`/docs`). |
| `HOST` | string | `"0.0.0.0"` | `"0.0.0.0"` | Public | ASGI bind IP address. |
| `PORT` | integer | `8000` | `8000` | Public | ASGI listening port. |
| `API_V1_STR` | string | `"/api/v1"` | `"/api/v1"` | Public | Root prefix for API version 1. |

### 2.2 Cryptography & Session Management
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `SECRET_KEY` | string | *Dev default* | Required (>= 32 chars) | **HIGH SECRET** | Master cryptographic key used for JWT signing and token hashing. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | integer | `15` | `15` | Public | JWT access token lifespan in minutes. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | integer | `7` | `7` | Public | Refresh token lifespan before mandatory re-authentication. |
| `RATE_LIMIT_ENABLED` | boolean | `true` | `true` | Public | Enforces sliding-window rate limiting on auth endpoints (`15 req/60s`). |

### 2.3 PostgreSQL Database & Connection Pooling
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `DATABASE_URL` | string | *sqlite* | Required (`postgresql+asyncpg://...`) | **HIGH SECRET** | Async database connection URI. |
| `DB_POOL_SIZE` | integer | `20` | `20` (or sized per core) | Public | Number of permanent connections in async pool. |
| `DB_MAX_OVERFLOW` | integer | `10` | `10` | Public | Maximum temporary connections above base pool during traffic spikes. |
| `DB_POOL_TIMEOUT` | integer | `30` | `30` | Public | Seconds to wait before failing with pool exhaustion timeout. |
| `DB_POOL_RECYCLE` | integer | `1800` | `1800` | Public | Seconds before recycling connections to avoid stale TCP sockets. |
| `DB_SSL_MODE` | enum | `None` | `"require"` | Public | SSL mode for PostgreSQL: `disable`, `prefer`, `require`, `verify-full`. |

### 2.4 Redis Cache & Celery Background Workers
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `REDIS_URL` | string | `"redis://localhost:6379/0"`| Required (`rediss://...`) | **SECRET** | Redis URI for caching and SSE ticket management. |
| `REDIS_SSL_CERT_REQS` | string | `None` | `"required"` | Public | SSL certificate verification mode for Redis TLS. |
| `CELERY_BROKER_URL` | string | `"redis://localhost:6379/1"`| Required (`rediss://...`) | **SECRET** | Celery task queue broker URI. |
| `CELERY_RESULT_BACKEND`| string | `"redis://localhost:6379/2"`| Required (`rediss://...`) | **SECRET** | Celery task result backend URI. |

### 2.5 Monitoring & Webhooks
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `ALERTMANAGER_HMAC_SECRET` | string | *Dev default* | Required (>= 32 chars) | **HIGH SECRET** | Shared secret used to verify HMAC-SHA256 signatures on Alertmanager webhooks. |
| `PROMETHEUS_URL` | string | `"http://localhost:9090"` | `"http://prometheus:9090"` | Internal | Internal URL for querying Prometheus metrics API. |
| `ALERTMANAGER_URL` | string | `"http://localhost:9093"` | `"http://alertmanager:9093"` | Internal | Internal URL for Alertmanager service. |

### 2.6 Autonomous Remediation Boundary
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `RECOVERY_SIMULATION_MODE` | boolean | `true` | `true` | Public | When `true`, remediation actions are safely simulated with audit logs and health checks without executing real host commands. |

### 2.7 AI Diagnosis Engine
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GEMINI_API_KEY` | string | `None` | Optional | **SECRET** | Google Gemini API key for intelligent incident root-cause diagnosis. |
| `AI_PROVIDER` | string | `"gemini"` | `"gemini"` | Public | Primary AI engine (`gemini` or `heuristic`). |
| `AI_TIMEOUT_SECONDS` | integer | `10` | `10` | Public | Timeout for AI inference before falling back to deterministic heuristic rules. |

### 2.8 Cookie Security & CORS
| Variable Name | Type | Default Value | Production Requirement | Sensitivity | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `COOKIE_SECURE` | boolean | `None` (auto) | `true` | Public | Enforces `Secure` flag on refresh cookies. |
| `COOKIE_SAMESITE` | enum | `None` (auto) | `"none"` or `"lax"` | Public | SameSite cookie policy (`none`, `lax`, `strict`). |
| `COOKIE_DOMAIN` | string | `None` | `".yourdomain.com"` | Public | Explicit domain scope for cross-subdomain authentication. |
| `CORS_ORIGINS` | list / string | *Localhost list* | `"https://app.yourdomain.com"` | Public | Trusted browser origins allowed to access the API. |

---

## 3. Frontend Environment Variables

| Variable Name | Sensitivity | Production Value | Purpose |
| :--- | :---: | :---: | :--- |
| `NEXT_PUBLIC_API_URL` | Public | `"https://api.yourdomain.com"` | Base URL for FastAPI backend endpoints. |

> [!WARNING]
> Never prefix sensitive credentials (HMAC secrets, JWT keys, database passwords) with `NEXT_PUBLIC_`. Doing so exposes the secret directly in client-side JavaScript bundles downloaded by all browser visitors.
