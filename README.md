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
|  6. Controlled Recovery Execution (Simulated Adapter)          |
|  7. Post-Recovery Health Verification -> Incident Resolved     |
|  8. Broadcast Real-Time SSE to Organization Subscribers        |
+--------------------------------+-------------------------------+
                                 ^
                                 | Bearer JWT (15m) + HttpOnly RTR
                                 | Server-Sent Events (SSE) Stream
                                 v
+----------------------------------------------------------------+
|                 Next.js 16 + React 19 Frontend                 |
|   (Overview, Services, Incidents, Recovery Center, Analytics,  |
|               Reports [PDF/JSON], Settings)                    |
+----------------------------------------------------------------+
```

---

## 2. Real-Time Server-Sent Events (SSE) Streaming

AutoHeal DevOps implements real-time data synchronization via Server-Sent Events (SSE).

### 2.1 Endpoint Specification
- **URL**: `GET /api/v1/events/stream`
- **Authentication**: JWT access token passed via `Authorization: Bearer <token>` or `?token=<jwt_access_token>`.
- **Tenant Isolation**: Events are strictly scoped to the authenticated caller's `organization_id`.
- **Keep-Alive**: Emits periodic `: keep-alive\n\n` comments every 15 seconds to prevent reverse proxy and browser timeouts.
- **Client Auto-Reconnect**: Reconnects with exponential backoff capped at 10 seconds.

### 2.2 Event Types
| Event Name | Description | Payload |
| :--- | :--- | :--- |
| `connected` | Handshake event on connection established | `{"status": "connected", "organization_id": "...", "timestamp": "..."}` |
| `incident_created` | Alertmanager webhook created a new incident | `{"id": "INC-...", "title": "...", "serviceName": "...", "severity": "...", "status": "open"}` |
| `incident_updated` | Incident status, diagnosis, or recovery state changed | `{"id": "INC-...", "status": "resolved", "recoveryStatus": "..."}` |
| `recovery_updated` | Recovery action approved, rejected, or executed | `{"id": "REC-...", "status": "completed", "verification": "passed", "durationSeconds": 35}` |
| `service_health` | Background telemetry scraper evaluated service SLA | `{"id": "...", "name": "...", "status": "healthy", "availability": 99.98, "errorRate": 0.12, "latencyMs": 142}` |

---

## 3. Frontend-Backend Integration & Architecture

### 3.1 Production vs. Demo Mode Separation
- **Production Mode**: Active by default when `NEXT_PUBLIC_API_BASE_URL` is set. Never silently falls back to mock data. If the backend is offline, a prominent connection error is presented.
- **Explicit Demo Mode**: Enabled only when `NEXT_PUBLIC_DEMO_MODE=true` (or when running locally without an API URL). Clearly labeled with `DEMO DATA` indicators.

### 3.2 Secure Authentication & Token Lifecycle
- **Access Tokens**: Short-lived (15 minutes), passed as `Authorization: Bearer <token>`.
- **Refresh Token Rotation (RTR)**: Long-lived (7 days), stored exclusively in secure `HttpOnly`, `SameSite=Lax` cookies scoped to `/api/v1/auth`. Never stored in `localStorage` or `sessionStorage`.
- **RTR Concurrency Lock**: Client-side deduplication guarantees that multiple simultaneous 401s execute only a single token rotation call, preventing race conditions and replay-attack lockouts.
- **Zero Master-Key Backdoor**: Authentication requires cryptographic JWT verification; internal master secrets cannot be passed as bearer tokens.

### 3.3 Connected Dashboard Views
1. **Overview Dashboard**: Displays real monitored services, healthy/degraded/down breakdown, active/critical incidents, verified recoveries, and dynamic recovery success rates.
2. **Monitoring**: Live CPU, memory, request rate, error rate, latency, and SLA availability.
3. **Services**: Service inventory with health status, metric history, environment filtering, and sorting.
4. **Incidents**: Correlated evidence, AI root-cause diagnosis, recommended actions, and incident timeline.
5. **Recovery Center**: Pending approvals, operator approval/rejection controls, simulated execution, and verification states.
6. **Analytics**: Real database-aggregated reliability trends, MTTR, false-positive rates, and CSV export.
7. **Reports**: Dual-format downloads for incident post-mortems (ReportLab binary PDF or structured JSON).
8. **Settings**: Non-sensitive workspace organization configuration, current user profile, and platform governance boundaries.

---

## 4. Recovery Action Allowlist & Safety Boundary

AutoHeal DevOps strictly enforces human-in-the-loop policy governance. Arbitrary shell commands, `eval`, and Docker socket mounting are completely blocked.

| Action Identifier | Display Name | Risk Level | Description |
| :--- | :--- | :--- | :--- |
| `restart_service` | Graceful Service Restart | Low | Simulates SIGTERM to workers, cycling containers, and re-binding socket listeners. |
| `clear_cache` | Purge Cache & Connection Pool | Low | Simulates evicting stale in-memory cache partitions and cycling database connection sockets. |
| `scale_service` | Horizontal Replica Scale-Up | Medium | Simulates scaling container deployment replicas from N to N+2 to absorb traffic surges. |
| `restore_health` | Reset Health Circuit Breaker | Low | Simulates tripping circuit breakers and flushing queue backlogs. |
| `rollback_release`| Rollback to Stable Release | High | Simulates reverting deployment container image to preceding verified semantic release tag. |

---

## 5. Environment Configuration

Configure `.env` in the repository root:

```bash
# Application
APP_ENV=development
DEBUG=True
PORT=8000
HOST=0.0.0.0
SECRET_KEY=your_cryptographically_secure_master_secret_32_chars_min

# Database & Cache
DATABASE_URL=postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db
REDIS_URL=redis://localhost:6379/0

# Authentication & Tokens
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# AI Diagnosis Provider
AI_PROVIDER=none          # 'gemini' (requires AI_API_KEY) or 'none' (deterministic heuristic fallback)
AI_API_KEY=your_gemini_api_key_here
AI_MODEL=gemini-1.5-pro
AI_TIMEOUT_SECONDS=8.0

# Monitoring & Alertmanager
PROMETHEUS_URL=http://localhost:9090
ALERTMANAGER_HMAC_SECRET=autoheal_alertmanager_webhook_hmac_secret_key_12345
METRIC_SCRAPE_INTERVAL_SECONDS=15
MAX_RECOVERY_RETRIES=3
RECOVERY_COOLDOWN_SECONDS=300

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_MODE=false
```

---

## 6. Windows PowerShell Startup Commands

### 6.1 Backend API Setup
```powershell
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Run database migrations
$env:PYTHONPATH="backend"
alembic -c backend/alembic.ini upgrade head

# 3. Seed initial database data
python backend/seed.py

# 4. Start FastAPI server
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

### 6.2 Background Worker & Scheduled Monitoring
```powershell
# Start Celery Worker
$env:PYTHONPATH="backend"
celery -A app.worker.celery_app worker --loglevel=info

# Start Celery Beat (schedules 15s periodic telemetry scrapes)
celery -A app.worker.celery_app beat --loglevel=info
```

### 6.3 Prometheus & Alertmanager
```powershell
# Prometheus Server
prometheus --config.file=monitoring/prometheus.yml

# Alertmanager Server
alertmanager --config.file=monitoring/alertmanager.yml
```

### 6.4 Frontend Development Server
```powershell
# Install frontend dependencies and start Next.js
npx pnpm install
npx pnpm dev
```
Access the dashboard at `http://localhost:3000`.

---

## 7. Testing & Verification

### 7.1 Full Backend Test Suite (56 Tests)
```powershell
$env:PYTHONPATH="backend"
.venv\Scripts\python.exe -m pytest backend/tests -v
```
All 56 tests pass, covering:
- AI Diagnosis & Prompt Injection Defense (`test_ai_diagnosis.py`)
- Alertmanager Ingestion & Deduplication (`test_alerts.py`)
- Core REST API Endpoints (`test_api.py`)
- Authentication, RTR, & Replay Attack Protection (`test_auth.py`)
- Security & Master-Key Bypass Prevention (`test_auth_security.py`)
- Complete 17-Step End-to-End Workflow (`test_e2e_workflow.py`)
- Monitoring Collector Telemetry (`test_monitoring.py`)
- Controlled Recovery Engine & Health Verification (`test_recovery_engine.py`)
- Workspace Settings Governance (`test_settings.py`)
- Real-Time Server-Sent Events (SSE) & Tenant Isolation (`test_sse.py`)

### 7.2 Frontend TypeScript Check & Next.js Production Build
```powershell
npx pnpm exec tsc --noEmit
npx pnpm run build
```

---

## 8. Known Limitations & Future Roadmap
- **Simulated Recovery Boundaries**: Recovery execution operates via strict safe simulation adapters. Future phases will integrate restricted mutual-TLS infrastructure agent runners.
- **SSE Transport**: Server-Sent Events serves as the primary real-time transport. WebSocket upgrades may be introduced if bidirectional low-latency terminal streaming is required.
- **Multi-Region Prometheus**: Currently integrates with one primary Prometheus endpoint; federated multi-cluster Prometheus support is on the roadmap.
