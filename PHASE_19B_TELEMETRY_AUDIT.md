# Phase 19B: Telemetry, Monitoring, and Alert-Delivery Architecture Audit

**Project:** AutoHeal DevOps
**Date:** 2026-11-22
**Status:** COMPLETE (Read-Only Audit)
**Mode:** `RECOVERY_SIMULATION_MODE=true` (Hard-Locked)

---

## Executive Summary

Phase 19B conducted a comprehensive, read-only architectural audit of the telemetry collection, metrics exposition, alert routing, webhook ingestion, frontend visualization, and testing infrastructure across the AutoHeal DevOps codebase.

The audit identified robust design foundations in webhook HMAC/Bearer authentication, alert deduplication, incident evidence binding, Server-Sent Events (SSE) notification streaming, and strict Docker socket isolation. Simultaneously, the audit revealed critical operational and architectural gaps, notably:
1. **Prometheus Scraping Target Gaps:** The isolated test service (`autoheal_test_service`) does not expose a `/metrics` endpoint and is not scraped by Prometheus.
2. **Configuration Disconnects:** Two distinct alert rule files exist (`monitoring/alerts.yml` and `monitoring/prometheus/alert_rules.yml`), but `monitoring/prometheus.yml` only includes `alerts.yml`, completely omitting enterprise platform SLO alerts.
3. **Synthetic Test Coupling:** All current webhook and alert integration tests operate via in-process FastAPI `TestClient` fixtures using synthetic mock JSON payloads; zero end-to-end network tests exist validating live Prometheus-to-Alertmanager-to-Backend HTTP delivery.
4. **Metric Fallback Synthesis:** In the absence of live Prometheus or Celery scraping cycles, backend API endpoints fall back to synthesized deterministic metric curves rather than explicit unavailable indicators.
5. **Runtime Container Inactivity:** In the current environment, Prometheus, Alertmanager, Celery, and Grafana are stopped; metrics collection is currently inactive.

---

## 1. Current Architecture Overview

```
                                  +---------------------------------------------+
                                  |            MONITORED TARGETS                |
                                  |                                             |
                                  |  +-------------------+  +----------------+  |
                                  |  |   FastAPI Backend |  | Sample Service |  |
                                  |  |   (/metrics)      |  | (/metrics)     |  |
                                  |  +---------+---------+  +--------+-------+  |
                                  +------------|---------------------|----------+
                                               | (HTTP Scrape 15s)   |
                                               v                     v
                                  +---------------------------------------------+
                                  |             PROMETHEUS ENGINE               |
                                  |                                             |
                                  |  Config: monitoring/prometheus.yml          |
                                  |  Rule Files: monitoring/alerts.yml          |
                                  |  Eval Interval: 15s                         |
                                  +----------------------+----------------------+
                                                         | Alert Firing (9093)
                                                         v
                                  +---------------------------------------------+
                                  |            PROMETHEUS ALERTMANAGER          |
                                  |                                             |
                                  |  Config: monitoring/alertmanager.yml        |
                                  |  Receiver: autoheal-webhook                 |
                                  |  Auth: Bearer token                         |
                                  +----------------------+----------------------+
                                                         | HTTP POST Webhook
                                                         v
                                  +---------------------------------------------+
                                  |            AUTOHEAL BACKEND API             |
                                  |                                             |
                                  |  Endpoint: /api/v1/alerts/webhook           |
                                  |  Auth Guard: verify_alertmanager_webhook    |
                                  |  Service: Incident Deduplication & AI Diag  |
                                  |  Storage: PostgreSQL + In-Memory SQLite     |
                                  +----------------------+----------------------+
                                                         |
                                  +----------------------+----------------------+
                                  |                                             |
                         SSE Event Stream                              Real-time Dashboard
                     /api/v1/events/stream                         Next.js App / SWR Data
                                  |                                             |
                                  v                                             v
                      +-----------------------+                     +-----------------------+
                      | Frontend Event Bridge |                     | Unified Observability |
                      +-----------------------+                     +-----------------------+
```

---

## 2. Component-by-Component Audit Findings

### 2.1 Prometheus Configuration & Scrape Targets

| Item | Expected Configuration | Discovered Configuration | Audit Assessment |
| :--- | :--- | :--- | :--- |
| **Config File** | `monitoring/prometheus.yml` | Present and valid YAML syntax | **VERIFIED** |
| **Global Timers** | `scrape_interval: 15s`, `evaluation_interval: 15s`, `scrape_timeout: 10s` | Matches expected standard | **VERIFIED** |
| **Alertmanager Target** | `alertmanager:9093` | Correctly defined under `alerting.alertmanagers` | **VERIFIED** |
| **Rule Files Included** | All active alert rules | Includes only `"alerts.yml"`; omits `"monitoring/prometheus/alert_rules.yml"` | **DEFECT** |
| **Backend Metrics Endpoint** | Scrape target on `autoheal-api:8000` | Scrapes `autoheal-api:8000/metrics` | **VERIFIED** |
| **Sample App Target** | Scrape target for sample microservice | Scrapes `checkout-api:8080`, but container name is `autoheal_sample_app` without network alias in `docker-compose.yml` | **MISCONFIGURATION** |
| **Fictitious Targets** | Monitored microservices | Targets `customer-web:8081` and `payments-api:8082` exist in config but have no container definitions in `docker-compose.yml` | **ORPHAN TARGETS** |
| **Isolated Test Service** | `autoheal_test_service:8080` | Not configured in `monitoring/prometheus.yml`; test service exposes no `/metrics` endpoint | **GAP** |
| **Live Metric Collection** | Active metric scraping | NOT VERIFIED in runtime (Prometheus container currently stopped; confirmed via `docker ps`) | **NOT VERIFIED** |

#### Detailed Analysis:
- `backend/app/main.py` properly exposes runtime telemetry at `GET /metrics` using an internal `TelemetryCollector` and `enterprise_metrics`.
- `test_environment/test_service/main.py` (`autoheal_test_service`) strictly exposes `/health`, `/status`, `/chaos/crash`, `/chaos/degrade`, and `/chaos/recover`. It contains **no `/metrics` endpoint**.
- `monitoring/test_services/server.py` implements a realistic Python HTTP server exposing standard Prometheus metric formats (`up`, `http_requests_total`, `http_request_duration_seconds_bucket`, `process_cpu_usage`, `process_resident_memory_bytes`), but is mapped only as `autoheal_sample_app` without network alias `checkout-api`.

---

### 2.2 Alertmanager Configuration & Alert Routing

| Item | Expected Configuration | Discovered Configuration | Audit Assessment |
| :--- | :--- | :--- | :--- |
| **Config File** | `monitoring/alertmanager.yml` | Present and valid YAML syntax | **VERIFIED** |
| **Group By** | Grouping by alert, service, environment | `["alertname", "service", "environment"]` | **VERIFIED** |
| **Timers** | `group_wait: 10s`, `group_interval: 30s`, `repeat_interval: 1h` | Configured appropriately for incident response | **VERIFIED** |
| **Webhook Destination** | `http://autoheal-api:8000/api/v1/alerts/webhook` | Correct internal Docker network URI | **VERIFIED** |
| **Authentication** | Bearer token or HMAC header | `bearer_token: "autoheal_dev_alertmanager_webhook_secret_32chars"` | **VERIFIED** |
| **Send Resolved** | Auto-resolution notification | `send_resolved: true` | **VERIFIED** |
| **Fallback / DLQ** | Secondary receiver or dead-letter destination | None configured; failed deliveries rely solely on Alertmanager retry loops | **RELIABILITY RISK** |
| **Alert Reachability** | Network route between containers | Routable on `autoheal_network`; not connected to isolated `autoheal_test_network` | **VERIFIED** |
| **Live Delivery Handling** | Failed delivery backoff & recovery | NOT VERIFIED in live runtime (Alertmanager container currently stopped) | **NOT VERIFIED** |

#### Detailed Analysis:
- Alertmanager is configured to push alerts with `Authorization: Bearer <token>`.
- The backend dependency `verify_alertmanager_webhook` accepts this Bearer token directly and compares it against `settings.ALERTMANAGER_HMAC_SECRET` using constant-time comparison (`hmac.compare_digest`).
- If the AutoHeal backend is unreachable, Alertmanager will retry at `group_interval` (30s) intervals up to `repeat_interval` (1h), but no dead-letter queue, persistent disk buffer, or fallback webhook (e.g. PagerDuty / Opsgenie / Slack direct) is configured.

---

### 2.3 Backend Ingestion, Authentication & Incident Lifecycle

| Item | Implementation | Code Location | Audit Assessment |
| :--- | :--- | :--- | :--- |
| **Webhook Endpoint** | `POST /api/v1/alerts/webhook` | `backend/app/api/routes/alerts.py` | **VERIFIED** |
| **Auth Dependencies** | `verify_alertmanager_webhook` | `backend/app/api/deps.py` | **VERIFIED** |
| **Supported Auth Methods** | `X-AutoHeal-Signature` (HMAC-SHA256), `X-Alertmanager-Secret`, `Authorization: Bearer` | `backend/app/api/deps.py:166-200` | **VERIFIED** |
| **Security Validation** | Insecure default secrets prohibited in `production`/`staging` | `backend/app/config.py:261-270` | **VERIFIED** |
| **Incident Deduplication** | Active incident check (`open`, `investigating`, `recovering`) | `backend/app/api/routes/alerts.py:100-110` | **VERIFIED** |
| **Firing Alert Handling** | Updates existing incident if active; creates `INC-<count>` if new | `backend/app/api/routes/alerts.py:145-194` | **VERIFIED** |
| **Resolved Alert Handling** | Transitions incident to `resolved`, records `resolved_at`, appends event | `backend/app/api/routes/alerts.py:112-143` | **VERIFIED** |
| **Evidence Persistence** | Stores `IncidentEvidence` (`kind="metric"`, `kind="log"`) | `backend/app/models/incident.py:134-180` | **VERIFIED** |
| **Timestamp Timezones** | Strict UTC timestamps (`DateTime(timezone=True)`) | `backend/app/models/incident.py:67-72` | **VERIFIED** |
| **AI Diagnosis Integration** | Triggers asynchronous AI root-cause analysis | `backend/app/services/ai/factory.py` | **VERIFIED** |
| **Error Isolation** | Catches AI diagnosis exceptions without aborting incident creation | `backend/app/api/routes/alerts.py:244-248` | **VERIFIED** |
| **SSE Event Broadcasting** | Broadcasts `incident_created` and `incident_updated` via Redis/Memory | `backend/app/services/events.py` | **VERIFIED** |

#### Detailed Analysis:
- The backend webhook pipeline is well-engineered. Alert deduplication ensures that flapping or sustained alerts do not spawn duplicate incident records for the same service.
- Evidence attachment accurately records the alerting query annotations as forensic metric evidence.
- Incoming severity is normalized (`_map_severity`) into standard AutoHeal categories (`critical`, `high`, `medium`, `low`).

---

### 2.4 Frontend Dashboards, Data Sources & Refresh Mechanics

| Item | Implementation | Code Location | Audit Assessment |
| :--- | :--- | :--- | :--- |
| **Dashboard Shell** | SWR-based data fetching | `components/dashboard/dashboard-view.tsx` | **VERIFIED** |
| **Real vs Demo Mode** | Conditioned on `NEXT_PUBLIC_DEMO_MODE` and backend URL | `lib/api/client.ts:12-18` | **VERIFIED** |
| **Demo Data Fallback** | Hardcoded mock objects in `lib/demo/mock-data.ts` | `lib/demo/mock-data.ts` | **VERIFIED** |
| **Realtime Refresh** | Server-Sent Events (`useRealtimeEvents`) | `lib/api/events.ts:21-100` | **VERIFIED** |
| **SSE Security** | Single-use tickets (`/api/v1/events/ticket`) to prevent JWT in URL logs | `lib/api/events.ts:48-63` | **VERIFIED** |
| **Reactive Invalidation** | SWR `mutate()` triggered on SSE events | `components/dashboard/dashboard-view.tsx:96-100` | **VERIFIED** |
| **Service Metrics Panel** | Queries `/api/v1/services/{id}/metrics` | `components/dashboard/data-views.tsx:141-163` | **VERIFIED** |
| **Backend Metric Synthesis** | Synthesizes 6-point fallback curve when DB has no samples | `backend/app/api/routes/services.py:159-178` | **SYNTHETIC BEHAVIOR** |

#### Detailed Analysis:
- The frontend cleanly decouples demo mode from live mode. If `NEXT_PUBLIC_API_BASE_URL` is set and `NEXT_PUBLIC_DEMO_MODE !== 'true'`, the dashboard requests live backend endpoints.
- When live incidents are created or updated, the backend pushes events through SSE, causing immediate SWR resource revalidation without requiring full-page polling.
- **Caveat:** If the backend database (`service_metrics` table) contains no scraped samples, `GET /api/v1/services/{id}/metrics` returns a hardcoded 6-point synthetic baseline (`base_val + 3`, `base_val + 7`, etc.) rather than an explicit "No telemetry collected" state.

---

### 2.5 Security, RBAC & Isolation Boundaries

| Item | Security Control | Discovered Implementation | Audit Assessment |
| :--- | :--- | :--- | :--- |
| **Webhook Ingestion Auth** | Timing-attack safe token/HMAC check | `hmac.compare_digest` in `verify_alertmanager_webhook` | **VERIFIED** |
| **SSE Stream Auth** | Ephemeral ticket exchange | Prevents authorization token exposure in query parameters | **VERIFIED** |
| **RBAC Enforcement** | Role requirements (`admin`, `operator`, `viewer`) | Enforced on operator endpoints via `RequireRole` | **VERIFIED** |
| **Secret Rotation & Defaults** | Rejection of dev secrets in production/staging | Pydantic `@model_validator` in `config.py` | **VERIFIED** |
| **Credential Masking** | Redaction of tokens, keys, passwords in logs | `mask_sensitive_data` in `backend/app/core/logging.py` | **VERIFIED** |
| **Docker Socket Isolation** | Socket unmounted from test runner & backend | Mounted strictly into `autoheal_socket_proxy` (UID 101) | **VERIFIED** |
| **Network Boundaries** | Air-gapped test network | `autoheal_test_network` has `internal: true` | **VERIFIED** |
| **Public Endpoint Exposure** | Exposure of `/metrics` and monitoring ports | `/metrics` is unauthenticated; Prometheus (9090), Alertmanager (9093), Grafana (3001) expose host ports | **SECURITY RISK** |
| **Simulation Mode Guard** | Safe recovery execution default | `RECOVERY_SIMULATION_MODE=true` hard-locked | **VERIFIED** |

#### Detailed Analysis:
- The system enforces excellent defense-in-depth regarding Docker socket isolation. The test runner and backend have zero direct access to the Docker socket.
- `RECOVERY_SIMULATION_MODE=true` remains hard-locked by default across all configuration layers.
- **Security Exposure Risk:** In `docker-compose.yml`, Prometheus (9090), Alertmanager (9093), and Node Exporter (9100) are mapped to `0.0.0.0` rather than `127.0.0.1`. In an untrusted network, these ports would expose operational topology and metrics.

---

### 2.6 Testing Strategy & Integration Gaps

| Test File | Scope | Test Type | Audit Assessment |
| :--- | :--- | :--- | :--- |
| `backend/tests/test_alerts.py` | Webhook auth, deduplication, resolved alerts | In-process synthetic `TestClient` | **VERIFIED (Unit/Component)** |
| `backend/tests/test_monitoring.py` | Telemetry probe, snapshot computation | Unit test with mocked `httpx` | **VERIFIED (Unit)** |
| `backend/tests/test_e2e_monitoring_healing.py` | Port security, webhook ingestion, AI diag, recovery | Mixed static analysis & synthetic `TestClient` | **VERIFIED (Component)** |
| `backend/tests/test_phase17_integration.py` | Post-recovery verification against `autoheal_test_service` | Live Docker container HTTP testing | **VERIFIED (Container Integration)** |
| **Prometheus $\to$ Alertmanager $\to$ Backend** | End-to-end telemetry alert pipeline | None exists | **MISSING INTEGRATION TEST** |
| **Alertmanager Failure / Retry** | Webhook network failure and redelivery | None exists | **MISSING RELIABILITY TEST** |

#### Detailed Analysis:
- **Synthetic vs Real Delivery:** All existing tests for Alertmanager webhook ingestion use FastAPI's in-memory `TestClient` with synthetic Python dictionary payloads. No test validates that a live Prometheus container evaluates rules, emits an alert to Alertmanager, and Alertmanager delivers the HTTP payload across a Docker bridge network.
- Integration tests in Phase 17 and Phase 18 verified the *downstream* recovery execution and verification against `autoheal_test_service`, but the *upstream* alert generation and ingestion chain remains verified only synthetically.

---

## 3. Working vs. Mocked / Simulated Functionality

### 3.1 Fully Functional & Implemented
1. **Webhook Authentication:** Dual-mode authentication supporting both shared Bearer tokens and HMAC-SHA256 signature headers with constant-time comparison.
2. **Incident Deduplication:** Prevents duplicate incident creation for active services; updates existing incident severity and logs re-trigger events.
3. **Auto-Resolution:** Automatically marks active incidents as `resolved` when Alertmanager delivers resolved alert notifications.
4. **Audit & Evidence Logging:** Structured persistence of forensic evidence records (`IncidentEvidence`) and timeline audit events (`IncidentEvent`).
5. **Real-time Event Streaming:** Server-Sent Events (SSE) broadcaster delivering live updates to connected frontends upon incident state transitions.
6. **Docker Socket Hardening:** L7 NGINX micro-proxy with unprivileged execution and mTLS, completely air-gapping the Docker daemon from the test runner.
7. **Post-Recovery Verification:** Hermetic fixtures validating HTTP 503 and HTTP 200 state transitions on `autoheal_test_service`.

### 3.2 Mocked or Simulated Functionality
1. **Backend Telemetry Metric Curve:** When `service_metrics` table has no recorded time-series entries, `GET /api/v1/services/{service_id}/metrics` returns a hardcoded 6-point synthetic baseline.
2. **Prometheus-to-Alertmanager Delivery in Tests:** Webhook ingestion tests rely entirely on synthetic payloads fed into `TestClient.post("/api/v1/alerts/webhook")`.
3. **Monitored Services:** Services `customer-web` and `payments-api` configured in `monitoring/prometheus.yml` have no corresponding containers and represent hypothetical targets.
4. **Recovery Actions:** Actual Docker container restarts remain completely simulated (`RECOVERY_SIMULATION_MODE=true`).

---

## 4. Identified Gaps & Vulnerabilities

### Priority 1: High Severity
- **GAP-19B-01: Omission of Enterprise Alert Rules in Prometheus:** `monitoring/prometheus.yml` only includes `alerts.yml`. The enterprise rules in `monitoring/prometheus/alert_rules.yml` (governing API 5xx rates, database connection pool exhaustion, mTLS certificate expiry, token replay attacks, and recovery failure rates) are **never loaded by Prometheus**.
- **GAP-19B-02: Scrape Target Hostname Mismatch:** In `docker-compose.yml`, the sample service is named `autoheal_sample_app` without the network alias `checkout-api`. Prometheus cannot resolve `checkout-api:8080`, leading to scrape failures.

### Priority 2: Medium Severity
- **GAP-19B-03: No Prometheus Telemetry on Test Service:** `autoheal_test_service` has no `/metrics` endpoint, precluding Prometheus from scraping its runtime health directly during integration testing.
- **GAP-19B-04: Host Port Exposure of Monitoring Infrastructure:** In `docker-compose.yml`, Prometheus (9090), Alertmanager (9093), and Node Exporter (9100) are bound to `0.0.0.0` instead of `127.0.0.1`.
- **GAP-19B-05: Absence of Alertmanager Fallback/DLQ Receiver:** If the AutoHeal API server is down or returns persistent 500 errors, Alertmanager has no secondary notification channel or dead-letter queue.

### Priority 3: Low Severity
- **GAP-19B-06: Synthetic Fallback in API Metrics:** `get_service_metrics` returns mock values instead of an explicit empty/unavailable response when no samples exist.
- **GAP-19B-07: Unauthenticated `/metrics` Endpoint:** `GET /metrics` on the backend API is unauthenticated; while standard for Prometheus, it exposes internal database pool metrics if published to untrusted networks.

---

## 5. Prioritized Implementation Plan

```
+---------------------------------------------------------------------------------------+
| PHASE 19C: TELEMETRY & ALERT CONFIGURATION REMEDIATION (Target: 1-2 Days)             |
| 1. Update monitoring/prometheus.yml to include monitoring/prometheus/alert_rules.yml. |
| 2. Add network alias 'checkout-api' to autoheal_sample_app in docker-compose.yml.     |
| 3. Bind Prometheus (9090) and Alertmanager (9093) host ports to 127.0.0.1.           |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| PHASE 19D: TEST SERVICE METRIC EXPOSITION (Target: 1 Day)                             |
| 1. Add Prometheus /metrics endpoint to test_environment/test_service/main.py.         |
| 2. Expose gauge 'autoheal_test_service_up' and counter 'http_requests_total'.        |
| 3. Add autoheal_test_service scrape target to test monitoring configuration.          |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| PHASE 19E: LIVE PIPELINE INTEGRATION TESTING (Target: 2 Days)                         |
| 1. Create test_phase19_e2e_alert_pipeline.py testing live alert delivery.             |
| 2. Trigger chaos degradation on test service -> Prometheus fires alert ->             |
|    Alertmanager dispatches webhook -> Backend creates deduplicated incident.          |
| 3. Verify complete chain end-to-end while keeping RECOVERY_SIMULATION_MODE=true.     |
+---------------------------------------------------------------------------------------+
```

---

## 6. Audit Verification Log & Constraints Checklist

- [x] **Read-only audit completed without modifying application code.**
- [x] **No Docker containers started, stopped, restarted, or created.**
- [x] **No recovery operations executed.**
- [x] **`RECOVERY_SIMULATION_MODE=true` preserved across all checks.**
- [x] **No database mutations performed.**
- [x] **No test suites executed during audit.**
- [x] **No Git staging, commits, pushes, or deployments performed.**
- [x] **All unverified runtime conditions explicitly flagged as NOT VERIFIED.**
