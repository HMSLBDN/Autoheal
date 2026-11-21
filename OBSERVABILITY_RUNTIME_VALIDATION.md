# OBSERVABILITY RUNTIME & DASHBOARD VALIDATION REPORT

**Project:** AutoHeal DevOps SaaS  
**Observability Stack:** OpenTelemetry Collector Contrib 0.96.0, Prometheus 2.51.0, Alertmanager 0.27.0, Jaeger 1.55, Grafana 10.4.0  
**Date:** 2026-11-21  
**Status:** VALIDATED (Real-Time Metrics, Alert Rules & Distributed Traces)

---

## 1. Executive Summary

Phase 12 verified that AutoHeal's observability pipeline operates end-to-end. Application telemetry flows from FastAPI and monitored services into the OpenTelemetry Collector, which sanitizes sensitive attributes before exporting metrics to Prometheus and distributed traces to Jaeger.

---

## 2. Telemetry Pipeline Architecture

```
[FastAPI Backend / Celery Worker / Monitored Services]
                     │
                     │ OTLP / gRPC (Port 4317)
                     ▼
       ┌───────────────────────────────┐
       │ OpenTelemetry Collector       │
       │ - Memory Limiter (75%)        │
       │ - Sensitive Attribute Redactor│
       │ - Batch Processor (1024)      │
       └───────┬───────────────┬───────┘
               │               │
  Metrics Port │ 8889          │ OTLP / gRPC
               ▼               ▼
      ┌─────────────────┐   ┌────────────────┐
      │ Prometheus 9090 │   │ Jaeger 16686   │
      │ Alert Evaluation│   │ Trace UI       │
      └────────┬────────┘   └────────────────┘
               │
               ▼
      ┌─────────────────┐
      │ Alertmanager    │
      │ (HMAC Webhooks) │
      └─────────────────┘
```

---

## 3. Grafana Dashboard Catalog

Grafana provisioning configurations in `monitoring/` provide operational dashboards:

1. **AutoHeal Core Platform Health:**
   - API Availability & Request Throughput (req/sec).
   - HTTP Latency Percentiles (p50, p95, p99).
   - HTTP 4xx / 5xx Error Rates.
2. **Database & Infrastructure Pool:**
   - PostgreSQL Active Connections & Checkout Wait Duration.
   - Redis Memory Consumption & Cache Hit/Miss Ratios.
   - Host CPU, Memory, and Root Disk Utilization.
3. **Incident & Autonomous Healing Operations:**
   - Active Incidents by Severity (Critical, High, Medium, Low).
   - Mean Time to Detection (MTTD) & Mean Time to Remediation (MTTR).
   - Simulated Recovery Success vs Failure Rates.
   - Celery Queue Depth & Worker Utilization.

---

## 4. Alert Rule Verification

Configured in `monitoring/alerts.yml`:
- `ServiceDown`: Fired when `up == 0` for $> 30\text{ seconds}$ (Severity: Critical).
- `HighErrorRate`: Fired when 5xx HTTP rate exceeds $5\%$ over $1\text{ minute}$ window (Severity: Critical).
- `LatencySpike`: Fired when p95 request duration exceeds $500\text{ ms}$ (Severity: Warning).
- `DiskSpaceLow`: Fired when node filesystem free space drops below $10\%$ (Severity: Warning).

All alerts deliver cryptographically signed payloads via Alertmanager to FastAPI webhook endpoint `/api/v1/alertmanager/webhook`.
