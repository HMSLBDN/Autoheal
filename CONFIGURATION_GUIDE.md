# AutoHeal DevOps — Configuration & Environment Reference

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1)  
**Applicability:** DevOps Administrators, Security Auditors, Deployment Engineers  
**Reference File:** `backend/app/config.py`  
**Safety Mandate:** `RECOVERY_SIMULATION_MODE=true` must remain active in all pilot and evaluation deployments.

---

## 1. Overview

AutoHeal DevOps employs a centralized, strongly typed configuration system powered by Pydantic v2 (`BaseSettings`). Settings are loaded from environment variables and `.env` files with priority given to system environment variables.

All configuration variables are validated at application startup. If a required variable is missing or violates type/format constraints, the backend fails fast with a clear, actionable diagnostic error.

---

## 2. Core Application Settings

| Variable | Type | Default | Description & Security Impact |
| :--- | :---: | :--- | :--- |
| `APP_NAME` | string | `"AutoHeal DevOps"` | Human-readable service name. |
| `APP_VERSION` | string | `"0.1.0"` | Platform semver string. |
| `APP_ENV` | string | `"development"` | Environment profile (`development`, `staging`, `production`, `test`). |
| `DEBUG` | boolean | `False` | Enables detailed stack traces and verbose debugging. Must be `false` in public pilots. |
| `HOST` | string | `"0.0.0.0"` | Network interface to bind HTTP listeners. |
| `PORT` | integer | `8000` | Port for FastAPI HTTP application. |
| `API_V1_STR` | string | `"/api/v1"` | Base prefix for version 1 REST routes. |
| `SECRET_KEY` | string | (Required) | Cryptographic key used for JWT signing and session integrity. Minimum 32 characters. |
| `RATE_LIMIT_ENABLED` | boolean | `True` | Activates token-bucket rate limiting across API endpoints. |
| `CORS_ORIGINS` | list | `["http://localhost:3000"]` | Allowed CORS origins for browser dashboard access. |

---

## 3. Database Settings (PostgreSQL 16)

AutoHeal uses asynchronous SQLAlchemy 2.0 with the `asyncpg` driver.

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | string | `postgresql+asyncpg://...` | Connection DSN. Format: `postgresql+asyncpg://user:pass@host:port/dbname`. |
| `DB_POOL_SIZE` | integer | `10` | Base number of concurrent database connections in pool. |
| `DB_MAX_OVERFLOW` | integer | `20` | Maximum bursting connections beyond `DB_POOL_SIZE`. |
| `DB_POOL_TIMEOUT` | integer | `30` | Seconds to wait before timing out on connection checkout. |
| `DB_POOL_RECYCLE` | integer | `1800` | Seconds after which idle connections are automatically recycled. |
| `DB_SSL_MODE` | string | `"prefer"` | SSL connection mode (`disable`, `prefer`, `require`, `verify-ca`, `verify-full`). |
| `DB_SSL_CA_CERT` | string | `None` | Path to TLS CA certificate file for database verification. |
| `DB_SSL_CLIENT_CERT`| string | `None` | Path to mTLS client certificate for database authentication. |
| `DB_SSL_CLIENT_KEY` | string | `None` | Path to mTLS client private key. |

---

## 4. Broker & Caching Settings (Redis 7.2 & Celery)

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `REDIS_URL` | string | `"redis://localhost:6379/0"` | Redis connection URL for caching, SSE ticket tracking, and distributed locks. |
| `CELERY_BROKER_URL` | string | `"redis://localhost:6379/0"` | Celery message broker queue URL. |
| `CELERY_RESULT_BACKEND`| string | `"redis://localhost:6379/0"`| Celery async task result backend. |
| `REDIS_SSL_CERT_REQS` | string | `None` | SSL certificate requirements for encrypted Redis connections (`CERT_REQUIRED`). |
| `REDIS_SSL_CA_CERTS` | string | `None` | Path to Redis TLS CA bundle. |

---

## 5. Security & Authentication Settings

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `JWT_ALGORITHM` | string | `"HS256"` | Cryptographic algorithm for JWT signatures (`HS256` or `RS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | integer | `30` | Lifespan of short-lived JWT access tokens. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | integer | `7` | Lifespan of rotating refresh tokens stored in HTTP-only cookies. |
| `SSE_TICKET_EXPIRE_SECONDS` | integer | `60` | Lifespan of single-use authentication tickets for SSE event streaming. |
| `COOKIE_SECURE` | boolean | `False` | Requires HTTPS for auth cookies. Set `True` in production. |
| `COOKIE_SAMESITE` | string | `"lax"` | SameSite policy (`lax`, `strict`, `none`). |
| `COOKIE_DOMAIN` | string | `None` | Restricts cookies to specific domain or subdomain hierarchy. |
| `FORWARDED_ALLOW_IPS` | string | `"*"` | Reverse proxy IP whitelist for X-Forwarded-For resolution. |
| `AGENT_SECRET_KEY` | string | (Required) | Shared HMAC secret for verifying communication with simulated agents. |

---

## 6. AI Diagnosis & Heuristic Fallback Settings

AutoHeal DevOps supports Google Gemini 1.5/2.0 for generating natural-language incident explanations and structured remediation hypotheses.

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `AI_PROVIDER` | string | `"gemini"` | AI service provider (`gemini` or `mock`). |
| `AI_API_KEY` | string | `""` | Google Gemini API key. If empty, the platform automatically engages deterministic heuristics. |
| `AI_MODEL` | string | `"gemini-1.5-flash"`| Model designation (`gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash`). |
| `AI_TIMEOUT_SECONDS` | integer | `10` | Maximum latency before aborting AI inference and triggering deterministic fallback. |

> [!NOTE]
> When `AI_API_KEY` is not provided or upstream API rate limits are hit, AutoHeal does **not** fail. It seamlessly activates the built-in deterministic heuristic rule engine, generating standard root-cause classifications based on HTTP status codes and metric anomalies.

---

## 7. Observability & Monitoring Settings

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `PROMETHEUS_URL` | string | `"http://localhost:9090"` | Upstream Prometheus query API URL. |
| `ALERTMANAGER_HMAC_SECRET` | string | (Required) | Shared HMAC-SHA256 secret for validating inbound Alertmanager webhook payloads. |
| `METRIC_SCRAPE_INTERVAL_SECONDS` | integer | `15` | Target frequency for polling microservice telemetry. |

---

## 8. Recovery Safety & Simulation Controls (Critical)

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `RECOVERY_SIMULATION_MODE` | boolean | `True` | **MANDATORY SAFETY LOCK.** When `True`, all recovery actions are handled by `SimulatedAgentClient`. No Docker daemon, shell, or host process is executed. |
| `DEMO_MODE_ENABLED` | boolean | `True` | Enables interactive chaos injection endpoints on the dashboard for demonstration. |
| `MAX_RECOVERY_RETRIES` | integer | `3` | Maximum number of recovery attempts permitted per incident before mandatory human escalation. |
| `RECOVERY_COOLDOWN_SECONDS` | integer | `120` | Enforced delay between consecutive recovery actions on the same service to prevent flapping. |

---

## 9. Configuration Profiles

### Profile A: Local Development / Evaluation (`.env.development`)
```env
APP_ENV=development
DEBUG=true
RECOVERY_SIMULATION_MODE=true
DEMO_MODE_ENABLED=true
COOKIE_SECURE=false
DATABASE_URL=postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db
REDIS_URL=redis://localhost:6379/0
```

### Profile B: Controlled Pilot Staging (`.env.pilot`)
```env
APP_ENV=staging
DEBUG=false
RECOVERY_SIMULATION_MODE=true
DEMO_MODE_ENABLED=true
COOKIE_SECURE=true
RATE_LIMIT_ENABLED=true
DATABASE_URL=postgresql+asyncpg://pilot_user:${PILOT_DB_PASS}@staging-db:5432/autoheal_pilot
REDIS_URL=redis://staging-redis:6379/0
```
