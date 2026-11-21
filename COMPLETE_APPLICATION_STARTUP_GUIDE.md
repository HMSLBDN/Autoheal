# COMPLETE APPLICATION STARTUP GUIDE

**Project:** AutoHeal DevOps SaaS  
**Version:** Phase 12 Production-Ready  
**Modes Supported:**  
1. **Containerized Mode (Docker Compose)**  
2. **Hybrid / Native Local Mode (Python Virtualenv + Node.js)**

---

## 1. Option A: Starting via Docker Compose (Recommended)

When Docker Desktop is running on your machine:

```bash
# Step 1: Clone and navigate to repository
git clone https://github.com/HMSLBDN/Autoheal.git
cd Autoheal

# Step 2: Validate configuration
docker compose config --dry-run

# Step 3: Launch all 14 services in detached mode
docker compose up -d --build

# Step 4: Verify health of running containers
docker compose ps

# Step 5: View real-time logs
docker compose logs -f backend
```

Access Points:
- Frontend Dashboard: `http://localhost:3000`
- FastAPI Documentation (Swagger): `http://localhost:8000/docs`
- Grafana Dashboards: `http://localhost:3001` (user: `admin`, pass: `admin_secure_pass`)
- Prometheus Metrics Explorer: `http://localhost:9090`
- Alertmanager Console: `http://localhost:9093`
- Jaeger Tracing UI: `http://localhost:16686`
- Sample Monitored Microservice: `http://localhost:8085`

---

## 2. Option B: Starting Native Local Development (No Docker Required)

If Docker Desktop is offline or for rapid local development:

### Terminal 1: FastAPI Backend
```bash
# Activate Python virtual environment
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

cd backend
$env:ENVIRONMENT="development"
$env:RECOVERY_SIMULATION_MODE="true"
$env:DATABASE_URL="sqlite+aiosqlite:///./autoheal_dev.db"

# Apply Alembic migrations
alembic upgrade head

# Launch Uvicorn server with hot-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2: Next.js Frontend
```bash
# In project root:
npm run dev
# Or for optimized production build:
npm run build
npm run start
```

### Terminal 3: Monitored Sample Microservice
```bash
.venv\Scripts\python.exe monitoring/test_services/server.py
# Listening on http://localhost:8080 (endpoints: /healthz, /metrics, /chaos/degrade, /chaos/fail, /chaos/recover)
```

---

## 3. Running Automated Self-Healing Tests

To execute the automated end-to-end self-healing demonstration:
```bash
.venv\Scripts\python.exe scripts/run_self_healing_demonstration.py
```

To execute the repeatable 12-step local demo runner:
```bash
.venv\Scripts\python.exe scripts/local_demo_runner.py
```
