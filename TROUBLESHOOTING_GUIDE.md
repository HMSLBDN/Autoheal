# AutoHeal DevOps — Troubleshooting & Diagnostic Guide

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1)  
**Applicability:** Operators, Evaluators, Deployment Engineers  
**Target:** Rapid triage and resolution of local installation and operational anomalies.

---

## 1. Quick Diagnostic Checklist

If experiencing unexpected behavior, run these initial diagnostics:

```bash
# 1. Check all container states
docker compose ps

# 2. Probe backend health endpoints
curl -s http://localhost:8000/api/v1/health | jq
curl -s http://localhost:8000/api/v1/health/liveness | jq
curl -s http://localhost:8000/api/v1/health/readiness | jq

# 3. Check backend and worker logs for errors
docker compose logs --tail=50 backend
docker compose logs --tail=50 celery_worker
```

---

## 2. Common Issues & Solutions

### Issue 1: Database Connection Refused (`[Errno 111] Connection refused`)
**Symptom:** Backend fails to start or `/api/v1/health/readiness` reports `database: unhealthy: ConnectionRefusedError`.
**Possible Causes:**
1. PostgreSQL container is still initializing or stopped.
2. Port 5432 is already bound by a local PostgreSQL installation.
**Resolution:**
```bash
# Check if container is running
docker compose ps db

# View database startup logs
docker compose logs db

# If running bare-metal, ensure PostgreSQL is started and matches DATABASE_URL in .env:
# postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db
```

### Issue 2: Pending Database Migrations
**Symptom:** API logs display `relation "..." does not exist` or `column "..." does not exist`.
**Cause:** Database schema has not been updated with the latest Alembic migrations.
**Resolution:**
Run migrations against the target database:
```bash
# From within the backend directory or container:
alembic upgrade head
```

### Issue 3: Redis or Celery Broker Connectivity Errors
**Symptom:** Background tasks (alert evaluations, health probes) do not execute, or readiness probe reports `redis: unhealthy: TimeoutError`.
**Possible Causes:**
1. Redis service not running on port 6379.
2. Celery worker crashed or disconnected.
**Resolution:**
```bash
# Restart Redis and Celery worker
docker compose restart redis celery_worker

# Verify Celery worker connection
docker compose logs celery_worker | grep "Connected to redis"
```

### Issue 4: Local Port Conflicts
**Symptom:** `docker compose up` reports `bind: address already in use` for ports 3000, 8000, 5432, or 6379.
**Resolution:**
Identify the conflicting process:
```bash
# On Linux/macOS:
lsof -i :3000
lsof -i :8000

# On Windows PowerShell:
Get-NetTCPConnection -LocalPort 8000,3000,5432,6379 -ErrorAction SilentlyContinue | Select-Object LocalPort,OwningProcess
```
Terminate the conflicting process or rebind ports in `.env` / `docker-compose.yml`.

### Issue 5: AI Provider Timeout or 429 Quota Exceeded
**Symptom:** Incident details show deterministic fallback explanation rather than LLM-generated narrative.
**Explanation & Behavior:**
This is **intended behavior**. When `AI_API_KEY` is omitted, or Google Gemini exceeds quota or times out (>10s), AutoHeal triggers the zero-downtime **Deterministic Heuristic Engine**. The incident still receives accurate root-cause classification and allowlist recovery recommendations. No crash occurs.

### Issue 6: Inbound Alert Webhook Rejection (`401 Unauthorized`)
**Symptom:** Alertmanager logs show `POST /api/v1/alerts/webhook` failing with status 401.
**Cause:** Mismatched `ALERTMANAGER_HMAC_SECRET` between Alertmanager configuration and `.env`.
**Resolution:**
Ensure `ALERTMANAGER_HMAC_SECRET` in `.env` matches the secret key configured in Alertmanager's webhook configuration.

### Issue 7: Next.js Frontend Hydration or Build Issues
**Symptom:** Frontend displays blank page or compilation error.
**Resolution:**
Clear Next.js build cache and recompile:
```bash
rm -rf .next
pnpm build
pnpm start
```

---

## 3. System Diagnostic Dump Script

To collect full system diagnostics for reporting or support, run:

```bash
#!/usr/bin/env bash
echo "=== AutoHeal DevOps Diagnostic Collection ==="
date -u
echo "--- Docker PS ---"
docker compose ps
echo "--- Health Status ---"
curl -s http://localhost:8000/api/v1/health
echo ""
echo "--- Readiness Status ---"
curl -s http://localhost:8000/api/v1/health/readiness
echo ""
echo "--- Recent Backend Logs ---"
docker compose logs --tail=30 backend
echo "--- Recent Worker Logs ---"
docker compose logs --tail=30 celery_worker
echo "=== End Diagnostics ==="
```
