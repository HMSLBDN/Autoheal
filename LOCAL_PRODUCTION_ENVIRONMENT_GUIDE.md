# LOCAL PRODUCTION ENVIRONMENT GUIDE

**Project:** AutoHeal DevOps SaaS  
**Version:** Phase 12  
**Target:** Local Production-Like Topology via Docker Compose & Native Microservices  
**Security Mode:** `RECOVERY_SIMULATION_MODE=true`

---

## 1. Architecture Overview

The local production-like environment mirrors a full cloud-native enterprise deployment. It comprises 14 modular services running on an isolated internal bridge network (`autoheal_network`):

```
                                [Browser / Client]
                                         │
                        HTTP 3000        │ HTTPS 443
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │       Next.js Production Runner (App)     │
                   └─────────────────────┬─────────────────────┘
                                         │ REST / WebSockets (8000)
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │         FastAPI Backend Server            │
                   └───────┬─────────────┬─────────────┬───────┘
                           │             │             │
        PostgreSQL 16      │             │ Redis 7     │ OTLP (4317/4318)
        (Internal)         ▼             ▼             ▼
       ┌──────────────────────┐   ┌────────────┐   ┌──────────────────────┐
       │   PostgreSQL 16 DB   │   │  Redis 7   │   │ OpenTelemetry        │
       │   (pgdata volume)    │   │  Queue/DB  │   │ Collector Contrib    │
       └──────────────────────┘   └─────┬──────┘   └──────────┬───────────┘
                                        │                     │
                     ┌──────────────────┴───────────────┐     │ Exporter (8889)
                     ▼                                  ▼     ▼
          ┌─────────────────────┐            ┌────────────────────┐
          │ Celery Async Worker │            │ Jaeger Tracing     │
          │ (AI Triage & Tasks) │            │ (UI: 16686)        │
          └─────────────────────┘            └────────────────────┘
                     │                                  │
                     ▼                                  │
          ┌─────────────────────┐                       │
          │ Celery Beat Cron    │                       │
          │ (Periodic Scrapes)  │                       │
          └─────────────────────┘                       │
                                                        │
┌───────────────────────────────────────────────────────┴─────────────────┐
│                           Observability Stack                           │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────┐  │
│  │ Prometheus (9090)     │  │ Alertmanager (9093)   │  │ Grafana     │  │
│  │ (Scrapes metrics)     │  │ (Delivers alerts)     │  │ (UI: 3001)   │  │
│  └───────────┬───────────┘  └───────────────────────┘  └─────────────┘  │
│              │                                                          │
│              ▼                                                          │
│  ┌───────────────────────┐  ┌───────────────────────┐                   │
│  │ Node Exporter (9100)  │  │ cAdvisor (8081)       │                   │
│  └───────────────────────┘  └───────────────────────┘                   │
│              ▲                                                          │
│              │ Scrape                                                   │
│  ┌───────────┴──────────────────────────────────────┐                   │
│  │ Sample Monitored App (checkout-api:8085)          │                   │
│  │ (Chaos Injection: /chaos/degrade, /chaos/fail)   │                   │
│  └──────────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Service Catalog & Internal Network Bindings

| Service Name | Image | Port (Host:Container) | Purpose / Role |
| :--- | :--- | :--- | :--- |
| `frontend` | `autoheal-frontend:latest` | `3000:3000` | Next.js production SSR dashboard |
| `backend` | `autoheal-backend:latest` | `8000:8000` | FastAPI async API server |
| `celery_worker` | `autoheal-celery-worker:latest` | *Internal* | Asynchronous incident triage & recovery worker |
| `celery_beat` | `autoheal-celery-beat:latest` | *Internal* | Periodic scheduler for background metrics |
| `db` | `postgres:16-alpine` | *Internal (pgdata)* | Relational database cluster with row-level tenant isolation |
| `redis` | `redis:7-alpine` | *Internal (redisdata)*| Task broker and caching engine with password protection |
| `prometheus` | `prom/prometheus:v2.51.0` | `9090:9090` | Timeseries metric scraper and alert rule evaluator |
| `alertmanager`| `prom/alertmanager:v0.27.0` | `9093:9093` | Alert routing and webhook dispatcher |
| `grafana` | `grafana/grafana:10.4.0` | `3001:3000` | Analytics dashboards and metric visualization |
| `node_exporter`| `prom/node-exporter:v1.7.0` | `9100:9100` | Host hardware & OS metric exporter |
| `cadvisor` | `gcr.io/cadvisor/cadvisor:v0.49.1`| `8081:8080` | Container resource usage & performance metrics |
| `otel_collector`| `otel/opentelemetry-collector-contrib:0.96.0` | `4317, 4318, 8889` | Distributed trace ingestion and PII attribute scrubbing |
| `jaeger` | `jaegertracing/all-in-one:1.55` | `16686:16686` | Distributed trace visualization and latency waterfall |
| `sample_app` | `autoheal-test-service:latest` | `8085:8080` | Monitored microservice with `/chaos` test endpoints |

---

## 3. Configuration Management & Environment Variables

Production environment variables are specified in `.env.production` (or managed dynamically via deployment orchestration):

```bash
# Core Application Environment
ENVIRONMENT=production
NODE_ENV=production
RECOVERY_SIMULATION_MODE=true

# Database Connection (Asyncpg)
DATABASE_URL=postgresql+asyncpg://autoheal_user:autoheal_secure_pass@db:5432/autoheal_db

# Redis Broker
REDIS_URL=redis://:redis_secure_pass@redis:6379/0

# Security Tokens
SECRET_KEY=autoheal_super_secret_jwt_key_min_32_chars_prod
ALERTMANAGER_WEBHOOK_SECRET=autoheal_alertmanager_hmac_secret_key_32chars

# Observability Integrations
PROMETHEUS_URL=http://prometheus:9090
ALERTMANAGER_URL=http://alertmanager:9093
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel_collector:4317
```

---

## 4. Startup Sequence & Verification

```bash
# Step 1: Validate Compose Specification
docker compose config --dry-run

# Step 2: Build & Start Full Environment in Detached Mode
docker compose up -d --build

# Step 3: Monitor Health Checks
docker compose ps

# Step 4: Verify Backend Health
curl http://localhost:8000/api/v1/health

# Step 5: Verify Frontend Dashboard
curl -I http://localhost:3000/
```
