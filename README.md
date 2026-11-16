# AutoHeal DevOps — AI-Assisted Self-Healing Platform

AutoHeal DevOps is a self-healing, AI-assisted platform designed to detect infrastructure regressions, provide automated root cause analysis, propose policy-governed remediation actions, and verify health recovery with human-in-the-loop approval.

---

## 1. System Architecture & Workflow

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
+--------------------------------+-------------------------------+
                                 ^
                                 | Bearer JWT (15m) + HttpOnly RTR
                                 v
+----------------------------------------------------------------+
|                 Next.js 16 + React 19 Frontend                 |
|       (Overview, Services, Incidents, Recovery Center, PDF)     |
+----------------------------------------------------------------+
```

---

## 2. Recovery Lifecycle & Safety Boundary

AutoHeal DevOps strictly enforces human-in-the-loop policy governance:

1. **Incident Detection**: Prometheus alert or telemetry SLA breach received via Alertmanager webhook.
2. **AI Diagnosis**: Gemini 1.5 Pro (or deterministic heuristic fallback) analyzes telemetry, error rate, latency, and deployment history to diagnose probable root cause.
3. **Recovery Recommendation**: AI proposes an action strictly validated against the **Recovery Action Allowlist**.
4. **Policy Validation**: Verifies cooldowns, maximum retries, and service policies.
5. **Human Approval**: Operator or Admin reviews diagnosis and explicitly approves or rejects the action via RBAC-protected endpoint.
6. **Controlled Recovery Execution**: Action executes via an isolated simulation adapter (zero arbitrary shell or Docker socket access).
7. **Post-Recovery Health Verification**: Real-time probes confirm SLA compliance (error rate < 0.5%, status healthy).
8. **Resolution or Escalation**: If verified healthy, incident status is marked `resolved`. If verification fails, the incident is escalated to on-call engineers.

> [!IMPORTANT]
> **Simulated Recovery vs. Real Infrastructure Recovery**:
> In the current stage, recovery actions execute through safe simulation adapters (`restart_service`, `clear_cache`, `scale_service`, `restore_health`, `rollback_release`). Arbitrary shell commands, `eval`, and Docker socket mounting are strictly blocked to protect host infrastructure. A restricted agent model will be plugged into this executor in future phases.

---

## 3. Approved Recovery Action Allowlist

| Action Identifier | Display Name | Risk Level | Description |
| :--- | :--- | :--- | :--- |
| `restart_service` | Graceful Service Restart | Low | Simulates SIGTERM to workers, cycling containers, and re-binding socket listeners. |
| `clear_cache` | Purge Cache & Connection Pool | Low | Simulates evicting stale in-memory cache partitions and cycling database connection sockets. |
| `scale_service` | Horizontal Replica Scale-Up | Medium | Simulates scaling container deployment replicas from N to N+2 to absorb traffic surges. |
| `restore_health` | Reset Health Circuit Breaker | Low | Simulates tripping circuit breakers and flushing queue backlogs. |
| `rollback_release`| Rollback to Stable Release | High | Simulates reverting deployment container image to preceding verified semantic release tag. |

---

## 4. Environment Variables

Configure `.env` in the repository root (see [`.env.example`](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/.env.example)):

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
AI_PROVIDER=gemini        # 'gemini' or 'none' (heuristic fallback)
AI_API_KEY=your_gemini_api_key_here
AI_MODEL=gemini-1.5-pro   # or gemini-1.5-flash
AI_TIMEOUT_SECONDS=8.0

# Monitoring & Alertmanager
PROMETHEUS_URL=http://localhost:9090
ALERTMANAGER_HMAC_SECRET=your_alertmanager_webhook_hmac_secret_key_12345
METRIC_SCRAPE_INTERVAL_SECONDS=15

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 5. Local Setup & Startup Commands

### 5.1 Prerequisites
- Python 3.12+
- Node.js 20+ & pnpm
- Redis (running locally or in Docker on port 6379)
- PostgreSQL (running locally or in Docker on port 5432)

### 5.2 Backend API Setup
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

### 5.3 Background Worker & Scheduled Monitoring
```powershell
# Start Celery Worker (handles monitoring, AI diagnosis, recovery tasks)
$env:PYTHONPATH="backend"
celery -A app.worker.celery_app worker --loglevel=info

# Start Celery Beat (schedules 15s periodic telemetry scrapes)
celery -A app.worker.celery_app beat --loglevel=info
```

### 5.4 Prometheus & Alertmanager (Monitoring Pipeline)
Start Prometheus and Alertmanager with the supplied configurations:
```powershell
# Prometheus Server
prometheus --config.file=monitoring/prometheus.yml

# Alertmanager
alertmanager --config.file=monitoring/alertmanager.yml
```

### 5.5 Frontend Development Server
```powershell
# Install frontend dependencies and start Next.js
npx pnpm install
npx pnpm dev
```

The frontend dashboard is accessible at `http://localhost:3000`.

---

## 6. Alertmanager Webhook Authentication

Alerts can be delivered to `POST /api/v1/alerts/webhook` via either:
1. **Shared Secret Header**:
   ```http
   POST /api/v1/alerts/webhook HTTP/1.1
   Host: localhost:8000
   X-Alertmanager-Secret: <ALERTMANAGER_HMAC_SECRET>
   Content-Type: application/json
   ```
2. **HMAC-SHA256 Payload Signature**:
   ```http
   POST /api/v1/alerts/webhook HTTP/1.1
   Host: localhost:8000
   X-AutoHeal-Signature: sha256=<HMAC_HEX_DIGEST>
   Content-Type: application/json
   ```

---

## 7. Testing & Verification

Run the full automated test suite (44 tests covering API, Auth, Monitoring, Alerts, AI Diagnosis, and Recovery Engine):

```powershell
$env:PYTHONPATH="backend"
.venv\Scripts\python.exe -m pytest backend/tests -v
```

Run TypeScript and Next.js production build verification:
```powershell
npx pnpm exec tsc --noEmit
npx pnpm run build
```

---

## 8. Known Limitations & Future Roadmap
- **Simulated Execution**: Recovery actions currently operate in deterministic safe simulation mode; real cloud/container agent execution will be introduced with explicit mutual TLS infrastructure daemons.
- **Single-Cluster Prometheus**: Currently integrates with one primary Prometheus endpoint; federated multi-cluster Prometheus support is planned for multi-region deployments.
- **Provider Adapters**: Gemini and deterministic heuristic engines are active; Anthropic Claude and OpenAI adapters are stubbed for future expansion.
