# AutoHeal DevOps — AI-Assisted Self-Healing Platform

AutoHeal DevOps is an end-to-end self-healing, AI-assisted platform designed to detect infrastructure regressions, provide automated root cause analysis, propose policy-governed remediation actions, and verify health recovery with human-in-the-loop approval.

---

## 1. System Architecture & Real-Time Workflow

```
                                 +-----------------------+
                                 |  Monitored Services   |
                                 | (checkout, web, pay)  |
                                 +-----------+-----------+
                                             |
                                    /metrics | /health
                                             v
+------------------+             +-----------------------+
|  AutoHeal Worker |<------------|      Prometheus       |
| (Celery + Redis) |  Telemetry  |   (Scrapes & Rules)   |
+--------+---------+  Collection +-----------+-----------+
         |                                   |
         | Periodic Cycle                    | Firing Alert
         v                                   v
+------------------+             +-----------------------+
|   PostgreSQL     |             |     Alertmanager      |
|  (16 Tables)     |             |   (Routing & HMAC)    |
+--------+---------+             +-----------+-----------+
         ^                                   |
         |                              POST | /api/v1/alerts/webhook
         |                                   v
+--------+-----------------------------------------------+
|                      AutoHeal FastAPI                          |
|                                                                |
|  1. Ingest Webhook Alert (HMAC SHA-256 / Secret Auth)          |
|  2. Deduplicate Alert -> Create/Update Incident                |
|  3. Trigger AI Diagnosis (Gemini 1.5 Pro / Heuristic Fallback) |
|  4. Validate Recommendation against Recovery Action Allowlist  |
|  5. Await Operator Approval (RBAC: operator / admin)           |
|  6. Restricted Infrastructure Agent Execution (mTLS / Signed)  |
|  7. Post-Recovery Health Verification -> Incident Resolved     |
|  8. Broadcast Real-Time SSE to Organization Subscribers        |
|  9. Deep Health & Readiness Probes (/health/readiness)         |
+--------------------------------+-------------------------------+
                                 ^
                                 | Bearer JWT (15m) + HttpOnly RTR
                                 | Single-Use SSE Ticket Stream (60s)
                                 v
+----------------------------------------------------------------+
|                 Next.js 16 + React 19 Frontend                 |
|   (Overview, Services, Incidents, Recovery Center, Analytics,  |
|               Reports [PDF/JSON], Settings)                    |
+----------------------------------------------------------------+
```

---

## 2. Docker & Containerization Architecture

AutoHeal DevOps provides production-grade, multi-stage Docker containerization running under unprivileged, non-root users with automated container health probes.

### 2.1 Multi-Stage Dockerfiles
- **Frontend (`Dockerfile`)**:
  - Base: `node:20-alpine`.
  - Non-root user: `nextjs` (UID 1001, GID 1001).
  - Standalone Next.js output (`output: 'standalone'`) yielding a compact, fast container image.
  - Healthcheck: Probes `http://127.0.0.1:3000/`.
- **FastAPI Backend (`backend/Dockerfile`)**:
  - Base: `python:3.12-slim`.
  - Non-root user: `autoheal` (UID 10001, GID 10001).
  - Two-stage wheel compilation: builds wheels in builder stage, copies only pre-built wheels to runner stage.
  - Healthcheck: Probes `http://127.0.0.1:8000/api/v1/health`.
- **Celery Background Worker (`backend/Dockerfile.celery_worker`)**:
  - Non-root user: `autoheal`.
  - Concurrency bounded (`--concurrency=4`).
  - Healthcheck: `celery_app.control.ping()`.
- **Celery Beat Scheduler (`backend/Dockerfile.celery_beat`)**:
  - Non-root user: `autoheal`.
  - Dispatches automated 15-second telemetry monitoring scrapes.

### 2.2 Security Rules Enforced
- **Zero Docker Socket Exposure**: The Docker socket (`/var/run/docker.sock`) is strictly NEVER mounted into any web application, Celery worker, or recovery executor container.
- **Unprivileged Non-Root Execution**: All application containers run under explicitly declared non-root system users.
- **Isolated Storage & Networks**: Internal bridge network `autoheal_network`; PostgreSQL and Redis have no public ports published to host interfaces in production.
- **Secret Hygiene**: `.dockerignore` excludes all `.env*` files, caches, virtual environments, and SQLite databases.

---

## 3. Docker Compose Infrastructure

AutoHeal DevOps provides two validated Docker Compose configurations:

### 3.1 Production Stack (`docker-compose.yml`)
Encompasses 11 interconnected microservices:
1. `frontend`: Next.js production runner (`3000:3000`).
2. `backend`: FastAPI async REST API (`8000:8000`).
3. `db`: PostgreSQL 16 Alpine with persistent volume `pgdata`, healthcheck `pg_isready`.
4. `redis`: Redis 7 Alpine with password authentication and persistent volume `redisdata`.
5. `celery_worker`: Distributed background task executor.
6. `celery_beat`: Periodic cron scheduler.
7. `prometheus`: Metrics collection and alerting server (`9090:9090`).
8. `alertmanager`: Webhook routing and HMAC distribution (`9093:9093`).
9. `grafana`: Metrics dashboards (`3001:3000`).
10. `node_exporter`: Host system telemetry exporter (`9100:9100`).
11. `cadvisor`: Container resource usage exporter (`8081:8080`).

### 3.2 Development Stack (`docker-compose.dev.yml`)
- Enables live hot-reloading for FastAPI backend and Celery workers via volume mounts (`./backend:/app`).
- Exposes PostgreSQL port `5432:5432` and Redis port `6379:6379` for local inspection tools.

---

## 4. Restricted Infrastructure Agent Architecture

AutoHeal implements a strict control-plane-to-execution-agent boundary (`app.services.agent`):
- **Cryptographic Request Envelopes**: Control plane dispatches requests signed with HMAC-SHA256 (`sign_payload`).
- **Replay Attack Prevention**: Every request envelope contains a single-use UUID nonce and ISO timestamp; nonces are tracked and duplicate nonces are rejected.
- **Clock Drift Protection**: Requests older than 300 seconds are rejected.
- **Strict Allowlisted Operations**: Agents execute ONLY enumerated primitives:
  - `restart_service`: Graceful restart with bounded grace periods (0–60s).
  - `scale_service`: Horizontal replica scaling strictly bounded (1–10 replicas).
  - `rollback_deployment`: Rollback to previous verified release tag.
  - `clear_cache`: Cache partition invalidation with approved key prefixes.
- **Zero Arbitrary Execution**: Arbitrary shell commands, `eval()`, unrestricted python code, and raw scripts are rejected.
- **Cryptographic Receipts**: Agents return exit codes, execution duration ms, sanitized stdout/stderr summaries, and a SHA-256 evidence receipt hash.
- **Simulated Adapter**: In development and initial rollout, `SimulatedAgentClient` executes safe simulated actions without modifying live hosts.

---

## 5. PostgreSQL Production Readiness & Backup / Restore

### 5.1 Async Connection Pooling
Configured in `app.database` and `app.config`:
- `pool_size`: 20 connections.
- `max_overflow`: 10 connections.
- `pool_timeout`: 30 seconds.
- `pool_recycle`: 1800 seconds (30 minutes).
- `pool_pre_ping`: True (detects and recycles severed connections before use).

### 5.2 Automated Database Backup
Script: `scripts/backup.ps1` / `backend/scripts/backup_db.py`
- Generates timestamped, compressed database dumps (`autoheal_backup_YYYYMMDD_HHMMSS.sql.gz` or `.sqlite.gz`).
- Computes SHA-256 checksum stored in `.sha256` files.
- Prunes backups older than retention window (default: 7 days).

```powershell
# Run manual database backup
.\scripts\backup.ps1 -OutputDir "./backups" -RetentionDays 7

# Dry-run validation
.\scripts\backup.ps1 -DryRun
```

### 5.3 Safe Database Restore
Script: `scripts/restore.ps1` / `backend/scripts/restore_db.py`
Enforces three strict safety guards:
1. **Target Confirmation**: Requires explicit `-ConfirmTargetDb <name>` matching the active database name.
2. **Production Safeguard**: If targeting a production or remote host, strictly requires `-ForceProductionRestore`.
3. **Safety Snapshot**: Automatically generates a pre-restore backup of the current database before applying any changes.

```powershell
# Restore database with target confirmation
.\scripts\restore.ps1 -BackupFile "./backups/autoheal_backup_20261117_044217.sql.gz" -ConfirmTargetDb "autoheal_db"
```

---

## 6. Redis & Celery Reliability

Configured in `app.worker`:
- `task_acks_late = True`: Tasks are acknowledged only after completion.
- `task_reject_on_worker_lost = True`: Re-queues tasks if a worker process crashes.
- `broker_connection_retry_on_startup = True`: Resilient connection retry during system initialization.
- `worker_prefetch_multiplier = 1`: Fair task distribution preventing queue starvation.
- `task_time_limit = 180`: Hard task timeout (3 minutes).
- `task_soft_time_limit = 120`: Soft task timeout (2 minutes).
- **Task Idempotency**: `execute_recovery_task` verifies if a recovery action was already completed or verified, preventing duplicate container cycling.
- **Dead-Letter Logging**: Unhandled exceptions and exhausted retries trigger `@signals.task_failure` hooks for audit logging.
- **Graceful Draining**: Worker drains active tasks on `SIGTERM` before terminating.

---

## 7. Hardened Authentication & Single-Use SSE Tickets

### 7.1 Single-Use SSE Ticket Security
To eliminate security risks from passing long-lived access tokens in URL query strings (which appear in access logs and browser history):
1. Client requests a ticket: `POST /api/v1/events/ticket` authenticated via `Authorization: Bearer <token>`.
2. Server generates a cryptographically random 32-byte ticket valid for 60 seconds.
3. Client connects to `GET /api/v1/events/stream?ticket=<ticket>`.
4. Server validates and **immediately burns (consumes)** the ticket upon connection handshake.
5. Replaying or reusing the same ticket is rejected with `HTTP 401 Unauthorized`.

### 7.2 Core Authentication Features
- **Argon2id** password hashing.
- **JWT Access Tokens** (15m expiry).
- **Refresh Token Rotation (RTR)** stored in `HttpOnly`, `SameSite=Lax` cookies.
- **RTR Concurrency Lock** preventing race conditions during simultaneous token refreshes.
- **No Master-Key Bypass**: All requests require valid cryptographic JWT verification.

---

## 8. Structured Logging & Observability

- **Correlation Tracing**: `RequestTracingMiddleware` injects a unique `X-Request-ID` into every HTTP response and logs latency in milliseconds.
- **Sensitive Data Masking**: Log formatters redact passwords, tokens, API keys, and credentials.
- **Health & Readiness Endpoints**:
  - `GET /api/v1/health`: Public service health probe.
  - `GET /api/v1/health/liveness`: Container liveness check for Kubernetes / Docker.
  - `GET /api/v1/health/readiness`: Deep dependency check verifying database (`SELECT 1`) and Redis connectivity.
- **Prometheus Scrapes**: Collects metrics from API, microservices, Node Exporter, and cAdvisor.

---

## 9. GitHub Actions CI/CD Pipeline

Defined in `.github/workflows/ci.yml`:
1. **`backend-quality`**:
   - Python 3.12 syntax verification (`python -m compileall`).
   - Alembic migration environment check.
   - Pytest suite execution across all 74 unit, integration, and security tests.
2. **`frontend-quality`**:
   - Node.js 20 + pnpm dependency installation.
   - TypeScript compilation (`pnpm exec tsc --noEmit`).
   - Next.js production build (`pnpm run build`).
3. **`docker-validation`**:
   - Production & Development Docker Compose syntax validation (`docker compose config`).
   - Backend and Frontend Docker image build validation.
4. **`security-audit`**:
   - Scans repository for committed `.env` files, private keys, or credentials.

---

## 10. Windows PowerShell Operations Guide

### 10.1 Running the Infrastructure via Docker Compose
```powershell
# Validate Compose files
docker compose -f docker-compose.yml config
docker compose -f docker-compose.dev.yml config

# Start full production stack
docker compose up -d

# Check running container health
docker compose ps
```

### 10.2 Local Development Startup (Without Docker)
```powershell
# 1. Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Start FastAPI Backend
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload

# 3. Start Celery Worker
$env:PYTHONPATH="backend"
celery -A app.worker.celery_app worker --loglevel=info

# 4. Start Next.js Frontend
npx pnpm dev
```

### 10.3 Database Migrations & Backup
```powershell
# Run database migrations
$env:PYTHONPATH="backend"
alembic -c backend/alembic.ini upgrade head

# Create database backup
.\scripts\backup.ps1 -OutputDir "./backups"

# Restore database from backup
.\scripts\restore.ps1 -BackupFile "./backups/autoheal_backup_20261117_044217.sql.gz" -ConfirmTargetDb "autoheal_db"
```

### 10.4 Running Tests
```powershell
# Run full backend pytest suite (143 tests)
.\.venv\Scripts\python -m pytest backend/tests -v

# Run frontend TypeScript typecheck
npx tsc --noEmit

# Run Next.js production build
pnpm run build
```

---

## 11. Test Coverage & Verification Summary

All 143 backend tests pass with zero failures:
- `test_agent_architecture.py`: Envelope signing, nonce replay rejection, timestamp drift, allowlist enforcement, simulated execution.
- `test_ai_diagnosis.py`: AI root cause analysis, prompt injection defense, heuristic fallback, allowlist enforcement.
- `test_alerts.py`: Webhook HMAC-SHA256 signature verification, incident deduplication, duplicate resolved alert protection.
- `test_analytics.py`: Mathematical accuracy of FPR ($FP / (FP + TN)$) and operator rejection separation.
- `test_auth.py` & `test_auth_security.py`: Argon2id, JWT validation, RTR rotation, replay detection, master-key bypass prevention.
- `test_backup_restore.py`: Backup generation, SHA-256 verification, retention pruning, 3-guard restore safety guards.
- `test_database_ssl_security.py`: SSL mode normalization, CA bundle validation, verify-ca/verify-full hostname verification.
- `test_docker_compose.py`: Compose service topology, security checks (no public db/redis ports in prod, zero Docker socket mounts, non-root users).
- `test_e2e_demo_lifecycle.py` & `test_e2e_workflow.py`: Complete 14-stage and 17-step end-to-end integration workflows.
- `test_events.py`: Incident events audit log, state transitions, tenant filtering.
- `test_frontend_secret_security.py`: Server-side-only webhook secret boundary, NEXT_PUBLIC_* variable allowlist enforcement, compiled bundle scan.
- `test_incidents.py`: Incident creation, status transitions, resolution verification.
- `test_readiness.py`: Public health, liveness, and deep database/redis readiness probes.
- `test_recoveries.py` & `test_recovery_engine.py`: Policy cooldown, RBAC approval gating, simulated recovery execution, post-recovery health verification.
- `test_redis_tls_security.py`: Rediss:// TLS validation, certificate verification enforcement in production, CA file validation.
- `test_reports.py`: PDF post-mortem generation and JSON export with organization scoping.
- `test_reverse_proxy_security.py`: Trusted proxy CIDRs and wildcard proxy rejection in production.
- `test_services.py`: Service registration, health state tracking, and metrics association.
- `test_settings.py`: Startup security fail-safes (HMAC secret enforcement, SECRET_KEY entropy & default check, wildcard proxy prevention).
- `test_sse.py` & `test_sse_ticket_security.py`: Server-Sent Events broadcasting, single-use ticket issuance, atomic burn on handshake.

---

## 12. Documentation & Operational Reference Index

Comprehensive guides covering architecture, deployment, security, and operation:

1. [ARCHITECTURE.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/ARCHITECTURE.md) — System architecture, data flow diagrams, component boundaries, and security topology.
2. [SECURITY.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/SECURITY.md) — Security policies, threat model, secret rotation procedures, and RBAC matrix.
3. [API_DOCUMENTATION.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/API_DOCUMENTATION.md) — Complete REST API reference, request/response schemas, and authentication headers.
4. [LOCAL_SETUP.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/LOCAL_SETUP.md) — Step-by-step local development setup with virtualenv, Node.js, and PowerShell instructions.
5. [DOCKER_SETUP.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/DOCKER_SETUP.md) — Multi-stage Docker build, container security, compose dev/prod environments, and healthcheck specs.
6. [MONITORING_SETUP.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/MONITORING_SETUP.md) — Prometheus scrape targets, alert rules, Alertmanager routing, and HMAC webhook authentication.
7. [RECOVERY_ENGINE.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/RECOVERY_ENGINE.md) — Action allowlist, simulation architecture, RBAC approval flow, and post-recovery verification.
8. [DATABASE_BACKUP_RESTORE.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/DATABASE_BACKUP_RESTORE.md) — PostgreSQL backup/restore procedures (`scripts/backup.ps1`, `scripts/restore.ps1`), pooling, and safety guards.
9. [TROUBLESHOOTING.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/TROUBLESHOOTING.md) — Common diagnostic scenarios (AppLocker, Docker named pipes, Redis TLS, SSE tickets) and verified fixes.
10. [PHASE_5_ACCEPTANCE_REPORT.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/PHASE_5_ACCEPTANCE_REPORT.md) — Itemized acceptance matrix with verification results and empirical evidence for all Phase 5 requirements.
11. [PHASE_6_READINESS_REPORT.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/PHASE_6_READINESS_REPORT.md) — 12-domain production readiness assessment and prioritized Phase 6 roadmap.
12. [DEMO_GUIDE.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/DEMO_GUIDE.md) — Guided walkthrough for live demonstration of fault injection, alert handling, AI diagnosis, and recovery.

