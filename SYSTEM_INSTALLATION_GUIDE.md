# AutoHeal DevOps — System Installation Guide

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1)  
**Applicability:** Local Evaluators, Pilot Testers, DevOps Engineers  
**Target Environment:** Local Workstations, Staging Sandboxes, CI Runners  
**Safety Notice:** Keep `RECOVERY_SIMULATION_MODE=true` at all times during pilot installations.

---

## 1. System Requirements

### Hardware Requirements
- **CPU:** 4 physical cores minimum (8 cores recommended for full Docker Compose stack).
- **RAM:** 8 GB minimum (16 GB recommended for concurrent Next.js, FastAPI, PostgreSQL, Redis, Prometheus, and Grafana).
- **Disk Space:** 15 GB available SSD storage.

### Software Prerequisites
- **Operating System:** Linux (Ubuntu 22.04+ / Debian 12+), macOS (13+ Ventura/Sonoma), or Windows 10/11 (with WSL2 enabled).
- **Container Runtime:** Docker Engine 24.0+ and Docker Compose v2.20+ (or Docker Desktop 4.25+).
- **Node.js Environment (for local frontend development):** Node.js v20.x LTS or v22.x LTS, with `pnpm` v9.x (`corepack enable pnpm` or `npm install -g pnpm`).
- **Python Environment (for local backend development):** Python 3.11 or 3.12, with `pip` and `virtualenv`.
- **Git:** Git 2.30+.

---

## 2. Repository Clone & Environment Setup

### Step 1: Clone Repository
```bash
git clone https://github.com/HMSLBDN/Autoheal.git
cd Autoheal
git checkout main
```

### Step 2: Initialize Environment Variables
Copy the baseline environment template:
```bash
cp .env.example .env
```

Ensure the safety configuration is locked in `.env`:
```env
# CRITICAL SAFETY LOCK
RECOVERY_SIMULATION_MODE=true
DEMO_MODE_ENABLED=true

# APPLICATION CORE
APP_NAME="AutoHeal DevOps"
APP_ENV=development
SECRET_KEY=change-this-in-production-use-a-32-byte-hex-string-minimum
PORT=8000
HOST=0.0.0.0

# DATABASE (PostgreSQL 16)
DATABASE_URL=postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db

# BROKER & CACHE (Redis 7.2)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# OBSERVABILITY & MONITORING
PROMETHEUS_URL=http://localhost:9090
ALERTMANAGER_HMAC_SECRET=simulation_alertmanager_hmac_secret_key_32chars
AGENT_SECRET_KEY=simulation_agent_secret_key_32chars

# AI DIAGNOSIS (Optional for pilot; deterministic fallback runs if unset)
AI_PROVIDER=gemini
AI_API_KEY=""
AI_MODEL=gemini-1.5-flash
```

---

## 3. Option A: Full-Stack Docker Deployment (Recommended)

The standard pilot deployment provisions all 14 containerized services via Docker Compose:

```bash
docker compose up -d
```

### Stack Composition
1. `frontend`: Next.js 16 Web Dashboard (`http://localhost:3000`)
2. `backend`: FastAPI Application Core (`http://localhost:8000`)
3. `celery_worker`: Background Task Consumer
4. `celery_beat`: Periodic Health & SLA Monitoring Scheduler
5. `db`: PostgreSQL 16 Relational Store (`localhost:5432`)
6. `redis`: Redis 7.2 Broker and State Cache (`localhost:6379`)
7. `prometheus`: Metric Scraper & Time-Series Engine (`http://localhost:9090`)
8. `alertmanager`: Alert Rule Evaluation & Webhook Dispatcher (`http://localhost:9093`)
9. `grafana`: Metric Dashboards (`http://localhost:3001`, admin/admin)
10. `node_exporter`: Host Machine Telemetry Collector (`localhost:9100`)
11. `cadvisor`: Container Resource Usage Telemetry (`localhost:8080`)
12. `otel_collector`: OpenTelemetry Collector (`localhost:4317` / `4318`)
13. `jaeger`: Distributed Trace Visualizer (`http://localhost:16686`)
14. `sample_app`: Target Microservice for Chaos Injection (`http://localhost:8085`)

### Verifying Container Health
```bash
docker compose ps
```
All containers should display state `Up` or `Up (healthy)`.

---

## 4. Option B: Local Development / Bare-Metal Deployment

For developers running services directly on the host machine with hot-reloading:

### Step 1: Start Supporting Infrastructure
Run PostgreSQL and Redis:
```bash
docker compose up -d db redis
```

### Step 2: Configure & Start Backend
Create Python virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# or .venv\Scripts\activate    # On Windows PowerShell

pip install -r backend/requirements.txt
```

Run database migrations:
```bash
cd backend
alembic upgrade head
cd ..
```

Start the FastAPI development server:
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

In a separate terminal, start the Celery worker:
```bash
celery -A backend.app.worker:celery_app worker --loglevel=info
```

### Step 3: Configure & Start Frontend
In another terminal, install and run Next.js:
```bash
pnpm install
pnpm dev
```
The frontend is accessible at `http://localhost:3000`.

---

## 5. Post-Installation Verification

Perform the following health checks to confirm all components are operational:

### 1. API Liveness & Readiness
```bash
curl -s http://localhost:8000/api/v1/health | jq
```
Expected output:
```json
{
  "status": "healthy",
  "environment": "development",
  "version": "0.1.0"
}
```

```bash
curl -s http://localhost:8000/api/v1/health/readiness | jq
```
Expected output when PostgreSQL and Redis are connected:
```json
{
  "status": "ready",
  "components": {
    "database": "healthy",
    "redis": "healthy"
  }
}
```

### 2. Frontend Accessibility
Open a web browser and navigate to `http://localhost:3000`. You should see the dark navy AutoHeal DevOps login portal.

### 3. Default Seed Credentials (Pilot Environment)
| Account Role | Username / Email | Password | Access Rights |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@autoheal.local` | `AutoHealAdmin2026!` | Full configuration, policies, user management, and recovery. |
| **Operator** | `operator@autoheal.local` | `AutoHealOperator2026!` | Incident triage, recovery approval, and experiment execution. |
| **Viewer** | `viewer@autoheal.local` | `AutoHealViewer2026!` | Read-only dashboards, incident timelines, and report inspection. |

---

## 6. Clean Shutdown and Data Persistence

### Graceful Stop (Preserves All Data)
To stop the application while preserving database tables, incidents, user records, and experiment history:
```bash
docker compose stop
```
Or:
```bash
docker compose down
```
> [!IMPORTANT]
> Never run `docker compose down -v` unless you intentionally wish to erase the PostgreSQL data volume (`db_data`) and Redis cache.

### Restarting the Stack
To resume the application:
```bash
docker compose up -d
```
All previously stored incidents, experiment runs, and user accounts remain fully intact.
