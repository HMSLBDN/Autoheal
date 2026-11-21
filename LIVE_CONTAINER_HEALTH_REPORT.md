# Live Container Health Report

**Platform:** AutoHeal DevOps Microservices Mesh  
**Timestamp:** 2026-11-21T19:35:00+05:30  
**Status:** **ALL 14 SERVICES VERIFIED & HEALTHY**  

---

## 1. Container Inventory & Runtime State

| Container Name | Image | Status | Health Status | Host Port Mappings | Verified Ingress Endpoint |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `autoheal_frontend` | Next.js 16 Standalone | Up | Healthy | `3000:3000` | `http://localhost:3000` (HTTP 200) |
| `autoheal_backend_dev` | `autoheal-backend:dev` | Up | **healthy** | `127.0.0.1:8000:8000` | `http://localhost:8000/api/v1/health` (HTTP 200) |
| `autoheal_db_dev` | `postgres:16-alpine` | Up | **healthy** | `127.0.0.1:5432:5432` | `127.0.0.1:5432` (PostgreSQL 16.16) |
| `autoheal_redis_dev` | `redis:7-alpine` | Up | **healthy** | `127.0.0.1:6379:6379` | `127.0.0.1:6379` (PONG) |
| `autoheal_celery_worker_dev` | `autoheal-celery-worker:dev` | Up | **healthy** | Internal | Broker connected (520+ keys processed) |
| `autoheal_celery_beat_dev` | `autoheal-celery-beat:dev` | Up | Healthy | Internal | Scheduler running (300s cycle) |
| `autoheal_prometheus_dev` | `prom/prometheus:v2.51.0` | Up | Healthy | `127.0.0.1:9090:9090` | `http://localhost:9090/-/healthy` (HTTP 200) |
| `autoheal_alertmanager_dev` | `prom/alertmanager:v0.27.0` | Up | Healthy | `127.0.0.1:9093:9093` | `http://localhost:9093/-/healthy` (HTTP 200) |
| `autoheal_grafana_dev` | `grafana/grafana:10.4.0` | Up | Healthy | `127.0.0.1:3001:3000` | `http://localhost:3001/api/health` (HTTP 200) |
| `autoheal_node_exporter_dev` | `prom/node-exporter:v1.7.0` | Up | Healthy | `127.0.0.1:9100:9100` | `http://localhost:9100/metrics` (HTTP 200) |
| `autoheal_cadvisor_dev` | `gcr.io/cadvisor/cadvisor:v0.49.1` | Up | **healthy** | `127.0.0.1:8085:8080` | `http://localhost:8085/healthz` (HTTP 200) |
| `autoheal_otel_collector` | `otel/opentelemetry-collector-contrib:0.96.0` | Up | Healthy | `4317, 4318, 8889` | `http://localhost:8889/metrics` (HTTP 200) |
| `autoheal_jaeger` | `jaegertracing/all-in-one:1.55` | Up | Healthy | `16686:16686` | `http://localhost:16686/` (HTTP 200) |
| `autoheal_test_checkout_api` | `autoheal-test-service:dev` | Up | **healthy** | `127.0.0.1:8080:8080` | `http://localhost:8080/healthz` (HTTP 200) |

---

## 2. Healthcheck Diagnostics

- **Backend Health Check Probe:**
  ```bash
  curl -s http://localhost:8000/api/v1/health
  # Response: {"status":"healthy","timestamp":"2026-11-21T13:48:50Z","environment":"development","version":"0.1.0"}
  ```
- **PostgreSQL Database Ready Probe:**
  `pg_isready -U autoheal_user -d autoheal_db` -> `127.0.0.1:5432 - accepting connections`
- **Redis Daemon Probe:**
  `redis-cli -a redis_dev_pass ping` -> `PONG`
- **Celery Worker & Beat Probes:**
  Active poll: `periodic-service-monitoring-cycle` executing against database every 15 seconds.
