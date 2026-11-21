# AutoHeal DevOps — Monitoring & Alerting Setup Guide

This guide details the Prometheus metrics scraping, alerting rules, Alertmanager webhook dispatch, and cryptographic authentication architecture in AutoHeal DevOps.

---

## 1. Monitoring Architecture Overview

```
+-------------------------------------------------------------+
|                     Monitored Services                      |
|  - FastAPI Backend (/metrics)     - Payment API (/metrics)  |
|  - Checkout Service (/metrics)    - Web Service (/metrics)  |
|  - Node Exporter (:9100)          - cAdvisor (:8080)        |
+------------------------------+------------------------------+
                               |
                   Scrape HTTP | 15s Interval
                               v
+-------------------------------------------------------------+
|                      Prometheus Server                      |
|  - Rule Evaluator: alerts.yml                               |
|  - TSDB: Time series metrics storage                        |
+------------------------------+------------------------------+
                               |
             Firing Alerts JSON| HTTP POST :9093
                               v
+-------------------------------------------------------------+
|                    Alertmanager Cluster                     |
|  - Grouping, Inhibiting, and Deduplication                  |
|  - Webhook Receiver with Bearer / HMAC Secret               |
+------------------------------+------------------------------+
                               |
             POST /api/v1/alerts/webhook
             Authorization: Bearer <ALERTMANAGER_HMAC_SECRET>
                               v
+-------------------------------------------------------------+
|                      AutoHeal FastAPI                       |
|  - Validates HMAC / Bearer Signature                        |
|  - Deduplicates Alert -> Incident Creation/Update           |
|  - Dispatches AI / Heuristic Root Cause Diagnosis           |
|  - Proposes Policy-Governed Recovery Remediation           |
+-------------------------------------------------------------+
```

---

## 2. Prometheus Configuration (`monitoring/prometheus.yml`)

### 2.1 Global Scrape Settings
- `scrape_interval`: 15s
- `evaluation_interval`: 15s

### 2.2 Scrape Targets
1. `autoheal-backend`: `backend:8000/metrics`
2. `node-exporter`: `node_exporter:9100/metrics`
3. `cadvisor`: `cadvisor:8080/metrics`
4. Sample services:
   - `web-frontend`: `web:8080/metrics`
   - `checkout-service`: `checkout:8080/metrics`
   - `payment-service`: `payment:8080/metrics`

---

## 3. Prometheus Alerting Rules (`monitoring/alerts.yml`)

AutoHeal defines alerting rules across latency, availability, error rates, and resource utilization:

### 3.1 ServiceDown (Critical)
Fires when a monitored service probe fails for more than 30 seconds.
```yaml
- alert: ServiceDown
  expr: up == 0
  for: 30s
  labels:
    severity: critical
  annotations:
    summary: "Instance {{ $labels.instance }} is down"
    description: "Service has been unreachable for more than 30 seconds."
```

### 3.2 HighErrorRate (Critical)
Fires when HTTP 5xx responses exceed 5% of total requests over a 2-minute rolling window.
```yaml
- alert: HighErrorRate
  expr: (sum(rate(http_requests_total{status=~"5.."}[2m])) by (service)) / (sum(rate(http_requests_total[2m])) by (service)) * 100 > 5
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "High 5xx error rate on {{ $labels.service }}"
    description: "5xx error rate is {{ $value | printf \"%.2f\" }}% (> 5%)."
```

### 3.3 HighLatency (Warning / Critical)
Fires when the p95 request latency exceeds 500ms for 2 minutes.
```yaml
- alert: HighLatency
  expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[2m])) by (le, service)) > 0.5
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High p95 latency on {{ $labels.service }}"
    description: "p95 latency is {{ $value | printf \"%.3f\" }}s (> 500ms)."
```

### 3.4 MemoryPressure (Warning)
Fires when service container memory usage exceeds 85% of allocated limits.
```yaml
- alert: MemoryPressure
  expr: container_memory_usage_bytes / container_spec_memory_limit_bytes * 100 > 85
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Container {{ $labels.name }} memory usage > 85%"
```

---

## 4. Alertmanager Webhook Routing (`monitoring/alertmanager.yml`)

Alertmanager deduplicates incoming alerts, groups them by incident fingerprint and service, and dispatches them via HTTP POST to the AutoHeal webhook endpoint:

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'service', 'severity']
  group_wait: 10s
  group_interval: 30s
  repeat_interval: 1h
  receiver: 'autoheal-backend-webhook'

receivers:
  - name: 'autoheal-backend-webhook'
    webhook_configs:
      - url: 'http://backend:8000/api/v1/alerts/webhook'
        send_resolved: true
        http_config:
          bearer_token: '${ALERTMANAGER_HMAC_SECRET:-autoheal_dev_alertmanager_webhook_secret_32chars}'
```

---

## 5. Webhook Security & HMAC Verification

FastAPI validates every incoming webhook request in `app.api.deps.verify_webhook_auth`:

1. **Authentication Headers**:
   - `Authorization: Bearer <token>` OR `X-Alertmanager-Signature: <hex_digest>`.
2. **Cryptographic Validation**:
   - The token is compared against `settings.ALERTMANAGER_HMAC_SECRET` using constant-time string comparison (`hmac.compare_digest`) to prevent timing side-channel attacks.
3. **Production Fail-Safe**:
   - In `production` or `staging`, the application strictly refuses to start if `ALERTMANAGER_HMAC_SECRET` is unset or matches known development defaults (`validate_security_settings`).
4. **Server-Side-Only Secret Boundary**:
   - Webhook authentication is strictly server-to-server between Alertmanager and FastAPI.
   - The webhook secret is **never** sent to the client browser, **never** embedded in `NEXT_PUBLIC_*` variables, and **never** stored in browser storage.
   - Frontend components communicate with the backend exclusively through authenticated REST endpoints using JWT access tokens.
   - Automated regression tests (`backend/tests/test_frontend_secret_security.py`) continuously enforce this boundary.

---

## 6. End-to-End Incident Lifecycle

When Alertmanager delivers an alert payload:
1. **Deduplication**:
   - An SHA-256 fingerprint is generated from `{service_id}:{alertname}:{labels}`.
   - If an active incident for this fingerprint exists, it is updated and new evidence is attached.
   - If the alert status is `resolved`, the incident status updates to `resolved` without reopening.
2. **Evidence Collection**:
   - Captured metrics, error logs, and timestamps are recorded in `incident_evidence`.
3. **AI Diagnosis & Recommendation**:
   - The incident is analyzed via Gemini 1.5 Pro or the deterministic heuristic engine.
   - A remediation action from the strict allowlist (`restart_service`, `scale_service`, `rollback_deployment`, `clear_cache`) is proposed.
4. **Human Operator Approval**:
   - Incident and proposed action are broadcast over SSE to connected dashboard operators.
   - Once approved, Celery executes the remediation action safely in simulation or via authenticated agent.
