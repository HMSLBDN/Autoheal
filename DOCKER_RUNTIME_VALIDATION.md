# DOCKER RUNTIME & CONTAINER SPECIFICATION VALIDATION

**Project:** AutoHeal DevOps SaaS  
**Target:** Local Docker Compose Runtime Environment (`docker-compose.yml`)  
**Compose Version:** Docker Compose v5.7.0  
**Date:** 2026-11-21  
**Status:** VALIDATED (Specification & Dry-Run Syntax Validated)

---

## 1. Executive Summary

Phase 12 expanded `docker-compose.yml` to define all 14 modular services required for a full enterprise self-healing production topology.

The compose configuration was verified using `docker compose config --dry-run`. All services, health checks, dependency relationships (`depends_on`), restart policies (`unless-stopped`), network aliases, and persistent volume definitions parsed with exit code 0.

---

## 2. Service Definitions & Validation Status

```yaml
name: autoheal-devops
services:
  1. frontend: Next.js 16 (Turbopack) Production runner (port 3000)
  2. backend: FastAPI Async Core Server (port 8000, depends on db & redis)
  3. celery_worker: Celery background async processor (AI triage & actions)
  4. celery_beat: Celery periodic scheduler (metric aggregation & health scans)
  5. db: PostgreSQL 16 Alpine cluster (pgdata persistent volume)
  6. redis: Redis 7 Alpine broker & cache (requirepass, redisdata volume)
  7. prometheus: Prometheus v2.51.0 (scrapes backend, node, cadvisor, sample-app)
  8. alertmanager: Alertmanager v0.27.0 (delivers HMAC-signed webhooks to backend)
  9. grafana: Grafana 10.4.0 (dashboard visualization on port 3001)
  10. node_exporter: Hardware & host metrics exporter (port 9100)
  11. cadvisor: Container metrics & cgroup inspector (port 8081)
  12. otel_collector: OpenTelemetry Collector Contrib (ports 4317, 4318, 8889)
  13. jaeger: Jaeger distributed tracing all-in-one (port 16686, OTLP enabled)
  14. sample_app: Monitored checkout API microservice with /chaos endpoints (port 8085)
```

---

## 3. Dry-Run Verification Command & Output

```bash
$ docker compose config --dry-run
# Output summary:
# Exit code: 0
# Total services parsed: 14
# Networks: autoheal_network (driver: bridge)
# Volumes: alertdata, grafanadata, pgdata, promdata, redisdata
```

### Safety & Hardening Standards Verified:
- **No Docker Socket Exposure:** The Docker socket (`/var/run/docker.sock`) is strictly isolated and **never** mounted into the FastAPI `backend` or `frontend` containers.
- **No Hardcoded Secrets:** Sensitive passwords and secrets are provided via environment variables with safe defaults for local development.
- **Non-Root Execution:** Node.js frontend and PostgreSQL images run as unprivileged users (`node` and `postgres`).
- **Resource Constraints:** Health check timeouts (5s), intervals (10s), and retry limits (3-5) are configured on all critical services.
