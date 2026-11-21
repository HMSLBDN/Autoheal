# AutoHeal DevOps — Local Development Setup Guide

This guide provides step-by-step instructions to set up, configure, and run AutoHeal DevOps directly on a local development workstation without Docker.

---

## 1. Prerequisites

Ensure the following tools and runtimes are installed on your system:

| Component | Minimum Version | Verified Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Python** | 3.12+ | 3.12.10 | FastAPI backend, Celery worker, AI reasoning engine |
| **Node.js** | 20 LTS+ | 20.x | Next.js 16 frontend |
| **pnpm / npm** | 9+ (pnpm) / 10+ (npm) | pnpm 9.x | Frontend package manager |
| **PostgreSQL** | 16+ | 16 Alpine | Primary multi-tenant relational database (or SQLite in-memory for testing) |
| **Redis** | 7+ | 7.2 | Celery task broker, results store, and token revocation store |
| **Git** | 2.40+ | Latest | Version control |

---

## 2. Repository Cloning & Structure

```bash
git clone https://github.com/HMSLBDN/Autoheal.git
cd autoheal-devops-saas
```

The repository structure:
- `backend/`: FastAPI application, Alembic database migrations, Celery worker/beat, unit & integration test suite.
- `app/`, `components/`, `lib/`: Next.js 16 + React 19 App Router frontend.
- `monitoring/`: Prometheus alert rules, Alertmanager configuration, sample service metrics exporter configs.
- `scripts/`: Operational scripts for database backup, restore, automated verification, and experiment harness.

---

## 3. Python Virtual Environment & Backend Setup

### 3.1 Create and Activate Virtual Environment

**Windows PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*Note on Windows Execution Policy:* If script execution is restricted, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

*Note on Windows AppLocker:* If binary execution in `.venv\Scripts\pytest.exe` or `uvicorn.exe` is restricted by application control policies, always execute via Python module syntax:
```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload
.\.venv\Scripts\python -m pytest backend/tests
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.2 Install Backend Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

---

## 4. Frontend Environment Setup

Install frontend dependencies using `pnpm` (recommended) or `npm`:

```bash
# Using pnpm
pnpm install

# Or using npm
npm install --legacy-peer-deps
```

---

## 5. Environment Variable Configuration

Create a local `.env` file in the project root by copying `.env.example`:

```powershell
Copy-Item .env.example .env
```

Key environment variables for local development:

```env
# Application Environment
APP_ENV=development
DEBUG=True
HOST=0.0.0.0
PORT=8000

# Security Keys (Generate strong 32+ character secrets)
SECRET_KEY=development_jwt_secret_key_must_be_at_least_32_characters_long
AGENT_SECRET_KEY=autoheal_agent_secret_key_32chars_long
ALERTMANAGER_HMAC_SECRET=autoheal_dev_alertmanager_webhook_secret_32chars

# Database & Broker (Development defaults)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/autoheal_db
REDIS_URL=redis://localhost:6379/0

# Safe Recovery & Demo Settings
RECOVERY_SIMULATION_MODE=true
DEMO_MODE_ENABLED=true

# AI Provider (Optional: gemini, openai, anthropic, or none for heuristic fallback)
AI_PROVIDER=none
AI_API_KEY=
```

> [!IMPORTANT]
> Keep `RECOVERY_SIMULATION_MODE=true` during all development and testing to ensure remediation commands execute as safe simulations without affecting live infrastructure.

---

## 6. Database Initialization & Migrations

If using PostgreSQL, create the database:
```sql
CREATE DATABASE autoheal_db;
```

Run database schema migrations to the latest revision:

**Windows PowerShell:**
```powershell
$env:PYTHONPATH="backend"
alembic -c backend/alembic.ini upgrade head
```

**macOS / Linux:**
```bash
PYTHONPATH=backend alembic -c backend/alembic.ini upgrade head
```

---

## 7. Starting the Application Services

To run the complete platform, start the four core components in separate terminal windows:

### 7.1 Backend API (FastAPI)
```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
- API root: `http://127.0.0.1:8000`
- Interactive OpenAPI Docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

### 7.2 Celery Distributed Task Worker
```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python -m celery -A app.worker.celery_app worker --loglevel=info --concurrency=2
```

### 7.3 Celery Beat Scheduler
```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python -m celery -A app.worker.celery_app beat --loglevel=info
```

### 7.4 Frontend Application (Next.js)
```powershell
pnpm dev
# or
npm run dev
```
- Web Application: `http://localhost:3000`

---

## 8. Verification & Running Tests

Verify your setup by executing the test suites:

### 8.1 Backend Automated Tests (136 Tests)
```powershell
.\.venv\Scripts\python -m pytest backend/tests -v
```

### 8.2 Frontend Type Checking & Production Build
```powershell
npx tsc --noEmit
pnpm build
```

---

## 9. Next Steps

- For containerized Docker deployment, see [DOCKER_SETUP.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/DOCKER_SETUP.md).
- To configure Prometheus and Alertmanager, see [MONITORING_SETUP.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/MONITORING_SETUP.md).
- For remediation action details, see [RECOVERY_ENGINE.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/RECOVERY_ENGINE.md).
