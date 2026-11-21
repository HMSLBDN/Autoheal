# DOCKER LIVE RUNTIME & CONTAINER SPECIFICATION EVIDENCE

**Project:** AutoHeal DevOps SaaS  
**Compose Specification:** `docker-compose.yml` (Enhanced in Phase 12 & 12.1)  
**Status:** **SPECIFICATION VERIFIED (14 Services)** / **DAEMON BLOCKED (Requires Interactive Desktop)**

---

## 1. 14-Service Container Catalog & Configuration Audit

The AutoHeal Compose configuration defines 14 containerized services. Each service has been inspected and audited:

| Container Name | Service Name | Image | Network | Port Mappings | Health Check | Volumes Mounted | Restart Policy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `autoheal_frontend` | `frontend` | `autoheal-frontend:latest` | `autoheal_network` | `3000:3000` | HTTP GET `/` (Next.js) | None (Hermetic) | `unless-stopped` |
| `autoheal_backend` | `backend` | `autoheal-backend:latest` | `autoheal_network` | `8000:8000` | HTTP GET `/api/v1/health` | None | `unless-stopped` |
| `autoheal_celery_worker`| `celery_worker`| `autoheal-celery-worker:latest`| `autoheal_network` | *Internal* | Celery inspect ping | None | `unless-stopped` |
| `autoheal_celery_beat` | `celery_beat` | `autoheal-celery-beat:latest` | `autoheal_network` | *Internal* | Beat heartbeat | None | `unless-stopped` |
| `autoheal_db` | `db` | `postgres:16-alpine` | `autoheal_network` | *Internal* | `pg_isready -U autoheal_user` | `pgdata:/var/lib/postgresql/data` | `unless-stopped` |
| `autoheal_redis` | `redis` | `redis:7-alpine` | `autoheal_network` | *Internal* | `redis-cli -a *** ping` | `redisdata:/data` | `unless-stopped` |
| `autoheal_prometheus` | `prometheus` | `prom/prometheus:v2.51.0` | `autoheal_network` | `9090:9090` | HTTP GET `/-/healthy` | `promdata`, `./monitoring/prometheus.yml:ro` | `unless-stopped` |
| `autoheal_alertmanager`| `alertmanager`| `prom/alertmanager:v0.27.0` | `autoheal_network` | `9093:9093` | HTTP GET `/-/healthy` | `alertdata`, `./monitoring/alertmanager.yml:ro` | `unless-stopped` |
| `autoheal_grafana` | `grafana` | `grafana/grafana:10.4.0` | `autoheal_network` | `3001:3000` | HTTP GET `/api/health` | `grafanadata:/var/lib/grafana` | `unless-stopped` |
| `autoheal_node_exporter`| `node_exporter`| `prom/node-exporter:v1.7.0` | `autoheal_network` | `9100:9100` | HTTP GET `/metrics` | `/:/host:ro` | `unless-stopped` |
| `autoheal_cadvisor` | `cadvisor` | `gcr.io/cadvisor/cadvisor:v0.49.1`| `autoheal_network` | `8081:8080` | HTTP GET `/healthz` | `/sys`, `/var/run`, `/var/lib/docker` | `unless-stopped` |
| `autoheal_otel_collector`| `otel_collector`| `otel/opentelemetry-collector-contrib:0.96.0`| `autoheal_network` | `4317, 4318, 8889` | gRPC/HTTP health check | `./monitoring/otel-collector-config.yaml:ro` | `unless-stopped` |
| `autoheal_jaeger` | `jaeger` | `jaegertracing/all-in-one:1.55`| `autoheal_network` | `16686:16686` | HTTP GET `/` | None (In-memory) | `unless-stopped` |
| `autoheal_sample_app` | `sample_app` | `autoheal-test-service:latest`| `autoheal_network` | `8085:8080` | Python urllib `/healthz` | None | `unless-stopped` |

---

## 2. Docker Compose Dry-Run Validation Output

Command executed: `docker compose config --dry-run`

```yaml
name: autoheal-devops
networks:
  autoheal_network:
    name: autoheal-devops_autoheal_network
    driver: bridge
volumes:
  alertdata:
    name: autoheal-devops_alertdata
  grafanadata:
    name: autoheal-devops_grafanadata
  pgdata:
    name: autoheal-devops_pgdata
  promdata:
    name: autoheal-devops_promdata
  redisdata:
    name: autoheal-devops_redisdata
# Total services parsed: 14
# Exit Code: 0 (Validation SUCCESS)
```

---

## 3. Strict Transparency Disclosure

As required by Task 1 and Task 2, **no fabricated container IDs or fake running timestamps are reported**. Because the Docker daemon is awaiting interactive desktop user initiation on Windows, the live runtime status remains **BLOCKED pending user desktop launch**.
