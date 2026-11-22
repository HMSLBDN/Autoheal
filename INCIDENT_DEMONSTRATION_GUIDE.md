# AutoHeal DevOps — Incident Demonstration Guide

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1)  
**Applicability:** Pilot Evaluators, Architecture Reviewers, Technical Evaluators  
**Estimated Time:** 15–20 minutes  
**Safety Mandate:** All remediation actions are executed in simulation mode (`RECOVERY_SIMULATION_MODE=true`). No host processes or Docker daemon sockets are touched.

---

## 1. Objective of Demonstration

This guide provides a reproducible, step-by-step walkthrough to demonstrate how AutoHeal DevOps:
1. Detects an infrastructure or application incident.
2. Ingests alerts and creates a tracked incident record.
3. Performs AI-assisted root-cause diagnosis (with deterministic fallback).
4. Enforces human-in-the-loop recovery authorization.
5. Safely executes bounded remediation via the simulation client.
6. Verifies service health restoration against SLO thresholds.
7. Maintains an immutable, tamper-evident audit record.
8. Enforces security boundaries against unauthorized actions.

---

## 2. Step 1: Environment Preparation & Startup

### Start Application Services
From the repository root:
```bash
docker compose up -d
```
Ensure all services are operational:
```bash
curl -s http://localhost:8000/api/v1/health | jq
```

### Log In to the Dashboard
1. Open `http://localhost:3000` in your web browser.
2. Sign in using the Operator account:
   - **Email:** `operator@autoheal.local`
   - **Password:** `AutoHealOperator2026!`

Verify that the dashboard displays the active service inventory with nominal SLO health (100%).

---

## 3. Step 2: Triggering a Controlled Sample Service Failure

There are two safe methods to simulate an incident:

### Method A: Direct Chaos Injection via Sample App Microservice
Inject an HTTP 503 outage into the running `sample_app` service (port 8085):
```bash
curl -X POST http://localhost:8085/chaos/503 \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 60, "error_rate": 100}'
```

### Method B: Via AutoHeal Demo Endpoint
Trigger a simulated incident payload directly through the API:
```bash
curl -X POST http://localhost:8000/api/v1/demo/trigger-incident \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "service_unavailable",
    "service_id": "checkout-api",
    "service_name": "Checkout API",
    "severity": "CRITICAL"
  }'
```

---

## 4. Step 3: Observing Alert Detection & Incident Creation

1. In the AutoHeal Dashboard, navigate to **Incidents** (`/dashboard/incidents`).
2. Within 5–15 seconds, a new incident appears:
   - **Title:** `Service Unavailable (HTTP 503 Spike)` on `checkout-api`
   - **Severity:** `CRITICAL`
   - **Status:** `investigating`
3. Click on the incident to open the **Incident Details** view.

---

## 5. Step 4: Inspecting Telemetry, Timeline & AI Diagnosis

1. **Timeline Inspection:** Observe the initial event: `Alert Triggered - High 503 rate detected by Prometheus`.
2. **Evidence Inspection:** Note the recorded metrics:
   - Pre-incident error rate: `100.0%` (SLO threshold: `1.0%`).
   - P95 Latency: `>3200 ms` (SLO threshold: `300 ms`).
3. **AI Root-Cause Analysis:**
   - Review the AI card. If a Google Gemini API key is configured, an LLM-generated explanation details the outage mechanism and downstream blast radius.
   - If no key is set or the API is unavailable, the **Deterministic Heuristic Engine** displays:
     > *"HTTP 503 availability failure on checkout-api. Upstream connection pool exhaustion detected. Recommended remediation: restart_container."*
   - Note the **Recommended Action:** `restart_container`.

---

## 6. Step 5: Authorizing & Executing Recovery

1. Click the **Approve Recovery** button on the Recommended Action card.
2. In the modal dialog:
   - Action: `restart_container`
   - Target Service: `checkout-api`
   - Notes: `"Approved by operator during pilot demonstration"`
3. Click **Confirm Execution**.

### What Happens Behind the Scenes:
- The backend checks RBAC: The Operator role is authorized to approve recoveries.
- The `RecoveryExecutor` dispatches the request to `SimulatedAgentClient`.
- The simulation client verifies the cryptographic HMAC signature and checks the action allowlist.
- It executes a non-destructive state-machine simulation and produces a SHA-256 evidence receipt.
- **Zero commands are executed against the host OS or Docker socket.**

---

## 7. Step 6: Post-Recovery Health Verification

1. Watch the incident status update in real time via Server-Sent Events (SSE).
2. The `PostRecoveryVerifier` automatically probes the service metrics:
   - Error rate drops from `100.0%` to `0.02%` (normalized).
   - P95 latency normalizes to `115 ms` (normalized).
3. The incident status transitions to **`resolved`**.
4. A new event is added to the timeline:
   - `Recovery Verified: checkout-api returned to healthy state. SLA restored.`
5. The recovery action card displays: **`Completed / Verified healthy`**.

---

## 8. Step 7: Inspecting the Audit Trail

1. Navigate to **Settings** $\to$ **Audit Logs** (or query `/api/v1/analytics/summary`).
2. Confirm the immutable records created during this walkthrough:
   - `incident_created` (Actor: `system_alertmanager`)
   - `recovery_approved` (Actor: `operator@autoheal.local`)
   - `recovery_dispatched` (Resource: `restart_container`, Target: `checkout-api`)
   - `recovery_verified` (Outcome: `passed`, Post-error: `0.02%`)

---

## 9. Step 8: Demonstrating Failure and Security Edge Cases

### Edge Case 1: Verification Failure Handling
Simulate a recovery action where service health fails to restore:
```bash
curl -X POST http://localhost:8000/api/v1/demo/trigger-incident \
  -H "Content-Type: application/json" \
  -d '{"scenario": "recovery_verification_failure"}'
```
- Approve the recommended action.
- The verifier detects that telemetry remains degraded above threshold.
- The recovery displays `Verification failed / Escalation required`.
- The incident status transitions to **`escalated`** with an on-call alert notification.

### Edge Case 2: Unauthorized Recovery Attempt (RBAC Rejection)
Log out and sign in as the **Viewer** user (`viewer@autoheal.local` / `AutoHealViewer2026!`).
Attempt to trigger an incident recovery via the API using the Viewer's JWT:
```bash
curl -X POST http://localhost:8000/api/v1/recoveries/{action_id}/approve \
  -H "Authorization: Bearer <VIEWER_JWT_TOKEN>"
```
**Expected Outcome:** HTTP `403 Forbidden` (`Detail: Insufficient permissions for recovery approval`). The Viewer role cannot approve or execute remediations.

### Edge Case 3: Unapproved Execution Rejection
Attempt to trigger an action without prior authorization:
```bash
curl -X POST http://localhost:8000/api/v1/recoveries/{action_id}/execute \
  -H "Authorization: Bearer <OPERATOR_JWT_TOKEN>"
```
**Expected Outcome:** HTTP `400 Bad Request` (`Detail: Action must be approved before execution`).

---

## 10. Step 9: Clean System Shutdown

When your evaluation is complete:
```bash
docker compose stop
```
All incident records, evidence, and audit logs are safely preserved in the PostgreSQL volume.
