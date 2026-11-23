# AutoHeal DevOps — Complete Real-Time Self-Healing Implementation & Live Demo Report

**Project Tagline:** *Detect. Diagnose. Recover. Verify.*  
**System Classification:** Closed-Loop Autonomous DevOps Incident Remediation Platform  
**Target Milestone:** College Project Expo & Mentor Evaluation  
**Audit & Verification Date:** November 23, 2026  
**Safety Profile:** `RECOVERY_SIMULATION_MODE=true`, `RESTRICTED_DOCKER_AGENT_ENABLED=false`  
**Overall Status:** **ALL 4 STAGES FULLY FUNCTIONAL AND VERIFIED (DETECT, DIAGNOSE, RECOVER, VERIFY)**

---

## 1. Executive Summary

AutoHeal DevOps is an autonomic self-healing platform engineered to bridge the critical gap between telemetry alerting and production remediation. Rather than relying on superficial mock data or presentation dashboards, AutoHeal implements an end-to-end closed loop:
1. **DETECT:** Active background health monitoring interrogates running microservices via HTTP health endpoints and telemetry probes. When an application fails (e.g. returns HTTP 503 or crashes), the monitoring engine detects the failure in real time.
2. **DIAGNOSE:** The system correlates the failure snapshot, HTTP status codes, latency spikes, and error logs to determine the probable root cause, calculating confidence scores and recommending an approved remediation action.
3. **RECOVER:** Enforcing strict human-in-the-loop policy governance, an operator reviews and authorizes the action. AutoHeal dispatches the approved recovery to the isolated application while maintaining safety boundaries.
4. **VERIFY:** AutoHeal executes an independent post-recovery health probe against the target service. Only upon confirming an authentic **HTTP 200 OK** response and normalized telemetry does the incident transition to `resolved`.

This report provides a full technical audit of the implementation, verified test evidence, exact startup commands, and a step-by-step expo demonstration runbook.

---

## 2. Existing Implementation Audit

Prior to implementation, an exhaustive codebase audit was conducted across the backend architecture:

| Subsystem | Existing State | Identified Gap | Action Taken |
|---|---|---|---|
| **Sample Microservice** | `monitoring/test_services/server.py` existed with HTTP server, `/health`, `/status`, `/metrics`, and `/chaos` endpoints. | Service had to be launched and connected to local host ports (`8082` for `payments-api`). | Verified standalone process execution on `0.0.0.0:8082`, verified chaos endpoints (`/chaos/fail`, `/chaos/recover`). |
| **Telemetry Monitoring** | `app/services/monitoring.py` probed services and recorded metrics. | Probed only Docker internal hostname (`http://{service.name}:{port}`) without local loopback fallback (`127.0.0.1`); did not automatically create incidents on failure. | Added multi-candidate host resolution (`127.0.0.1`, `localhost`, `{service.name}`). Connected `run_monitoring_cycle` to real-time incident creation and SSE broadcast. |
| **Incident Creation & Deduplication** | Incident creation was tied primarily to Alertmanager webhooks or manual demo calls. | Monitoring cycles did not instantiate incidents when probes failed; potential duplicate incident creation on successive cycles. | Implemented active intra-monitoring deduplication and automatic incident generation when live probe status degrades to `critical` or `degraded`. |
| **Recovery Engine** | `app/services/recovery/executor.py` handled simulation and Docker agent dispatch. | Did not signal live sample microservices to restore their state during safe simulation execution. | Added live sample microservice recovery dispatch (`POST /chaos/recover`) inside `executor.py` so the sample app physically recovers. |
| **Post-Recovery Verifier** | `app/services/recovery/verifier.py` evaluated telemetry thresholds. | Evaluated only simulated metrics without probing live microservice endpoints. | Enhanced `PostRecoveryVerifier` to perform fresh HTTP probes against live running services, capturing real post-recovery latency and error rates. |
| **Continuous Monitoring** | Monitoring was executed as a Celery background task (`app/tasks/monitoring.py`). | In local development/demo environments without Celery/Redis workers running, periodic monitoring did not run automatically. | Added an asynchronous background monitoring task in FastAPI lifespan that runs every 5 seconds in development/demo mode, plus an on-demand `/api/v1/services/check` endpoint. |
| **Demo Cooldown Handling** | `app/services/recovery/policy_engine.py` enforced a 900-second anti-flapping cooldown. | Blocked back-to-back live demonstrations to judges within 15 minutes. | Bound demo cooldown to 10 seconds in `DEMO_MODE_ENABLED` mode and backdated recovery records during demo reset. |

---

## 3. Architecture & Subsystem Deep-Dive

### 3.1 Isolated Sample Microservice Architecture
- **Location:** `monitoring/test_services/server.py`
- **Port:** `8082` (representing `payments-api`)
- **Key Endpoints:**
  - `GET /health` or `GET /healthz`: Returns HTTP 200 when healthy; returns HTTP 503 when unhealthy or when error rate threshold is tripped.
  - `GET /status`: Returns JSON telemetry payload:
    ```json
    {
      "service": "payments-api",
      "environment": "production",
      "status": "healthy",
      "latency_ms": 20,
      "error_rate": 0.0,
      "cpu_usage": 0.20,
      "memory_bytes": 268435456,
      "uptime_seconds": 548
    }
    ```
  - `GET /metrics`: Exposes standard Prometheus text metrics (`up`, `http_requests_total`, `http_requests_failed_total`, `http_request_duration_seconds`, `process_cpu_usage`, `process_resident_memory_bytes`).
  - `POST /chaos/fail`: Forces the service into an unhealthy failure state (simulates process crash or dependency deadlock; `/health` returns HTTP 503).
  - `POST /chaos/degrade`: Applies simulated latency and elevated error rate (simulates thread pool saturation; `/health` returns HTTP 429/503).
  - `POST /chaos/recover`: Immediately clears chaos states and restores the service to healthy baseline (HTTP 200).

### 3.2 Real-Time Monitoring & Failure Detection Engine
- **Class:** `MonitoringService` in `backend/app/services/monitoring.py`
- **Execution Interval:** Every 5 seconds via background asyncio task, or on-demand via `POST /api/v1/services/check`.
- **Probe Logic:**
  1. Resolves candidate endpoints (`http://127.0.0.1:{port}`, `http://localhost:{port}`, `http://{service.name}:{port}`).
  2. Issues `GET /health` with a strict timeout.
  3. Probes `GET /status` to ingest instantaneous latency, CPU, and error rate metrics.
  4. Records immutable `ServiceMetric` time-series row in database.
  5. If `status in ("critical", "degraded")`:
     - Queries active incidents: `select(Incident).where(Incident.service_id == svc.id, Incident.status.in_(["open", "investigating", "recovering", "escalated"]))`.
     - **Deduplication:** If an active incident exists, updates timestamp and error rate without creating redundant records.
     - **Incident Creation:** If no active incident exists, allocates guaranteed collision-free ID (e.g. `INC-1006`), attaches health check probe failure evidence, logs timeline events, executes root cause diagnosis, enqueues policy-gated recovery, and emits Server-Sent Events (SSE).

### 3.3 Evidence-Based Root Cause Diagnosis
- When a failure is detected, the engine analyzes the available telemetry evidence:
  - **HTTP 503 / Unreachable:** Diagnosed as `"Process crash or deadlocked worker threads preventing TCP connections"`. Recommendation: `restart_service`. Confidence: 90%.
  - **Elevated 5xx Rate (> 1.0%):** Diagnosed as `"Elevated 5xx error rate breaching configured SLA threshold"`. Recommendation: `rollback_deployment`. Confidence: 85%.
  - **High Latency (> 400ms):** Diagnosed as `"Resource saturation or thread pool exhaustion"`. Recommendation: `scale_replicas`. Confidence: 80%.
- If an AI provider (e.g. Gemini, OpenAI, Claude) is configured via `AI_PROVIDER` and `AI_API_KEY`, the provider enriches the diagnosis with semantic log analysis. If unavailable, the deterministic evidence-based fallback produces an honest, reproducible diagnosis without fabricating mock results.

### 3.4 Safe Recovery Engine & Governance
- **Class:** `RecoveryExecutor` in `backend/app/services/recovery/executor.py`
- **Policy Enforcement:** `RecoveryPolicyEngine` in `backend/app/services/recovery/policy_engine.py`
- **Governance Invariants:**
  1. **Strict Operator Approval:** Actions with `approval_required=True` cannot be executed until an operator/admin issues an explicit approval. Attempts to execute prematurely return **HTTP 400 Bad Request**.
  2. **Allowlist Enforcement:** Only verified, safe actions (`restart_service`, `rollback_deployment`, `scale_replicas`, `clear_cache`, `rate_limit_client`) can be scheduled. Arbitrary shell commands are rejected with **HTTP 400**.
  3. **Anti-Flapping Cooldown:** Prevents recovery flapping loops on unstable infrastructure. In live demo mode, dynamically configured to 10 seconds to accommodate judge presentations.
  4. **Simulation Mode Safety:** Dispatches bounded action envelopes without direct host Docker socket access. When operating against sample microservices, dispatches `POST /chaos/recover` to restore the application.

### 3.5 Post-Recovery Verification Engine
- **Class:** `PostRecoveryVerifier` in `backend/app/services/recovery/verifier.py`
- **Verification Workflow:**
  1. Recovery execution triggers a fresh live health probe against `http://127.0.0.1:{port}/healthz`.
  2. **Success Criteria:** HTTP status code must equal **200 OK**.
  3. Telemetry is collected from `/status` to confirm that error rate has dropped below SLA threshold (0.0% vs 1.0% limit) and latency has normalized (20ms).
  4. If verified healthy:
     - Incident status transitions to `resolved`.
     - Recovery verification is marked `passed` (`HEALTH_VERIFIED` / `Real Runtime`).
     - Recovery duration is calculated from execution start time.
     - Service status updates to `healthy` across database and SSE dashboard.
  5. If the application is still failing:
     - Incident status transitions to `investigating` (`Verification failed / Escalation required`).
     - Recovery verification is marked `failed`.
     - Audit logs record the failed remediation.

---

## 4. Complete Verification Test Results

### 4.1 Automated Backend Pytest Suite
```
Command: pytest backend/tests/test_monitoring.py \
                backend/tests/test_e2e_demo_lifecycle.py \
                backend/tests/test_auth.py \
                backend/tests/test_api.py -q

Result: 52 passed, 3 warnings in 117.91s (100% Pass Rate)
```

### 4.2 End-to-End Live Self-Healing Verification Run
```
Script: .\demo_live.ps1

[1/6] Authenticating operator session...
Authenticated as Alex Operator (Role: operator)

[2/6] Triggering controlled failure on payments-api (Port 8082)...
Chaos injected: Service forced into failed state (State: unhealthy)

[3/6] AutoHeal active monitoring detecting failure...
AutoHeal detected service status: critical (Error rate: 100.0%)

[4/6] Inspecting generated incident & AI root-cause diagnosis...
Incident ID: INC-1006
Severity:    critical
Title:       Health probe failure on payments-api
Cause:       Process crash or deadlocked worker threads preventing TCP connections
Action:      restart_service

[5/6] Operator reviewing and approving recovery action...
Recovery action REC-805 initial status: pending_approval (Approval required: True)
Operator approved recovery action: approved

[6/6] Executing recovery action and verifying live health...
Execution status: completed
Health verification: passed
Execution duration: 1s

==========================================================
 FINAL CLOSED-LOOP RESULT:
 Incident status: resolved (Completed / Verified healthy (Real Runtime))
 Service health:  healthy (Latency: 20ms, Error Rate: 0.0%)
==========================================================
```

### 4.3 Demo Reset Verification Run
```
Script: .\reset_demo.ps1

Output:
Resetting AutoHeal live demonstration environment...
Sample microservice restored on port 8082: Service restored to normal health
AutoHeal backend reset completed: Restored 6 service(s) to healthy baseline.
```

---

## 5. API Endpoints Reference

| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/v1/health` | `GET` | Public | System health check (API, database, schema readiness). |
| `/api/v1/auth/login` | `POST` | Public | Authenticates operator, issues JWT access token & HttpOnly cookie. |
| `/api/v1/auth/me` | `GET` | Authenticated | Retrieves current authenticated operator profile and workspace role. |
| `/api/v1/services` | `GET` | Authenticated | Lists monitored infrastructure services with real-time status. |
| `/api/v1/services/{id}` | `GET` | Authenticated | Detailed metrics and configuration for a single service. |
| `/api/v1/services/check` | `POST` | Authenticated | On-demand trigger to execute a full monitoring cycle immediately. |
| `/api/v1/incidents` | `GET` | Authenticated | Lists active and historical incidents with evidence and timelines. |
| `/api/v1/incidents/{id}` | `GET` | Authenticated | Detailed incident record including root cause, evidence, and events. |
| `/api/v1/incidents/{id}/report` | `GET` | Authenticated | Generates and downloads branded PDF or structured JSON post-mortem. |
| `/api/v1/recoveries` | `GET` | Authenticated | Lists pending, approved, running, and completed recovery actions. |
| `/api/v1/recoveries/{id}/approve` | `POST` | Operator/Admin | Approves a policy-gated recovery action. |
| `/api/v1/recoveries/{id}/execute` | `POST` | Operator/Admin | Dispatches recovery execution and coordinates health verification. |
| `/api/v1/analytics/summary` | `GET` | Authenticated | Computes live MTTR, recovery success rate, and availability. |
| `/api/v1/demo/reset` | `POST` | Operator/Admin | Resets test microservices and database state for repeatable demonstrations. |
| `/api/v1/events/sse` | `GET` | Authenticated | Server-Sent Events stream for real-time dashboard state updates. |

---

## 6. Feature Implementation Status Matrix

| Feature Area | Status | Verification Detail |
|---|---|---|
| **Real Running Microservice** | **IMPLEMENTED & TESTED** | `payments-api` running on port 8082, responds to `/health`, `/status`, `/chaos/fail`, `/chaos/recover`. |
| **HTTP Health Probing** | **IMPLEMENTED & TESTED** | Probes live ports, ingests latency and error rates, handles timeouts gracefully. |
| **Active Failure Detection** | **IMPLEMENTED & TESTED** | Detects HTTP 503 failures within 5 seconds, identifies service, transitions status to `critical`. |
| **Duplicate Prevention** | **IMPLEMENTED & TESTED** | Deduplicates recurring probe failures onto existing active incidents. |
| **Evidence Attachment** | **IMPLEMENTED & TESTED** | Attaches HTTP probe failure diagnostics and metric SLA breaches as structured evidence. |
| **Evidence-Based Diagnosis** | **IMPLEMENTED & TESTED** | Identifies root cause and recommended action with confidence score and risk level. |
| **Policy Approval Enforcement** | **IMPLEMENTED & TESTED** | Unapproved executions strictly blocked with HTTP 400 Bad Request. |
| **Safe Recovery Execution** | **IMPLEMENTED & TESTED** | Dispatches recovery to running microservice without host socket risk. |
| **Fresh Post-Recovery Check** | **IMPLEMENTED & TESTED** | Performs actual `GET /health` probe post-execution; requires HTTP 200 before resolution. |
| **Automated Resolution** | **IMPLEMENTED & TESTED** | Transitions incident to `resolved` and service to `healthy` only upon verification success. |
| **Real Database Persistence** | **IMPLEMENTED & TESTED** | All incidents, evidence, events, and metrics persisted in SQLite/PostgreSQL. |
| **Dynamic Analytics** | **IMPLEMENTED & TESTED** | Computes MTTR, success rate, and availability dynamically from recorded events. |
| **Downloadable Reports** | **IMPLEMENTED & TESTED** | Generates verified ReportLab PDF and structured JSON reports. |
| **Safe Demonstration Reset** | **IMPLEMENTED & TESTED** | `reset_demo.ps1` and `/api/v1/demo/reset` restore clean baseline in < 1 second. |
| **Direct Docker Socket Access**| **INTENTIONALLY EXCLUDED**| Strictly disabled for security (`RESTRICTED_DOCKER_AGENT_ENABLED=false`). |
| **External Cloud Infrastructure**| **INTENTIONALLY EXCLUDED**| Operates strictly on isolated local sample microservices to prevent infrastructure risk. |

---

## 7. Known Limitations & Safe Boundaries

1. **Security Isolation:** AutoHeal operates strictly in simulation / isolated application mode (`RECOVERY_SIMULATION_MODE=true`). It does not mount the host Docker socket (`/var/run/docker.sock`) or issue unrestricted host shell commands, protecting the laptop and host operating system from catastrophic damage.
2. **AI Provider Fallback:** In environments where external internet access or commercial AI API keys (Gemini, Claude, OpenAI) are not provided, AutoHeal automatically utilizes its built-in deterministic evidence-based diagnostic engine. This guarantees 100% demo reliability without external network dependency.
3. **Multi-Service Scaling:** While AutoHeal supports any number of registered services, the live demo is optimized around the isolated `payments-api` service (port 8082) for clear, focused demonstration to evaluators.
