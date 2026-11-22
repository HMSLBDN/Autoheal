# AutoHeal DevOps — Recovery Failure Handling & Resilience Matrix

**Document Version:** 1.0.0  
**Phase:** Phase 16 — Controlled Real Infrastructure Integration & Production Readiness  
**Target:** SRE Runbook, Failure Modes & Effects Analysis (FMEA)  

---

## 1. Core Failure Handling Philosophy

1. **Fail-Closed Principle:** Any ambiguity in authorization, signature, container identity, or operation parameters must halt execution immediately.
2. **Restart Does Not Equal Recovery:** Successfully executing a container restart (`exit_code=0`) never resolves an incident. The incident is only resolved if post-restart telemetry and application health probes independently confirm SLA restoration.
3. **No Fabricated Rollbacks:** Operations that alter external process state (e.g. restarting a container) are inherently non-reversible. AutoHeal does not invent speculative "rollback" mechanisms for physical process restarts.
4. **Guaranteed Auditability:** Every failure, rejection, or timeout is captured in immutable audit logs with SHA-256 evidence hashes and failure diagnostics.

---

## 2. Exhaustive Failure Matrix (13 Failure Conditions)

| # | Failure Condition | Detection Mechanism | Immediate Agent Action | Control Plane / Incident Action | Reversibility |
| :-: | :--- | :--- | :--- | :--- | :---: |
| **1** | **Agent Unavailable** | HTTP connect timeout / connection refused at `DOCKER_AGENT_URL`. | N/A (Agent unreachable). | Recovery marked `failed`. Incident remains `investigating`. Escalation timer continues. | N/A |
| **2** | **Authentication Failure** | HMAC-SHA256 signature mismatch against `AGENT_SECRET_KEY`. | Returns HTTP 401. Increments `requests_rejected_total`. | Recovery marked `rejected`. Security alert emitted. Incident remains `investigating`. | Reversible (No action taken) |
| **3** | **Invalid Request** | Missing fields, bad JSON, or schema validation error. | Returns HTTP 400. Records audit event. | Recovery marked `failed`. Incident remains `investigating`. | Reversible (No action taken) |
| **4** | **Expired Request** | Timestamp drift $> 300\text{s}$ ($|t_{\text{agent}} - t_{\text{req}}| > 300$). | Returns HTTP 401 (`Timestamp drift exceeds threshold`). | Prevents execution of stale actions. Incident prompts operator to re-verify. | Reversible (No action taken) |
| **5** | **Replay Attempt** | Request `nonce` found in `_SEEN_NONCES` cache. | Returns HTTP 401 (`Nonce already processed`). | Rejection logged as replay attempt. Action discarded. | Reversible (No action taken) |
| **6** | **Unauthorized Operation** | Action not in `ALLOWED_OPERATIONS` (e.g. `exec_bash`, `rm`). | Returns HTTP 403 (`Action not in allowlist`). | Recovery marked `rejected`. High-severity security audit event logged. | Reversible (No action taken) |
| **7** | **Container Not Found** | Docker API returns HTTP 404 for requested container name. | Returns HTTP 404 with error summary. | Recovery marked `failed`. Diagnostic output attached to incident. | Reversible (No action taken) |
| **8** | **Container Identity Mismatch** | Target container not in `APPROVED_CONTAINERS` or matches `CRITICAL_PROTECTED_CONTAINERS`. | Returns HTTP 403 (`Container not approved`). | Execution aborted. Operator notified of target policy violation. | Reversible (No action taken) |
| **9** | **Restart Timeout** | Docker Engine does not respond within `timeout_seconds + 5s`. | Docker socket connection timed out; returns status `timeout`. | Recovery marked `timeout`. Retry counter incremented. If max retries reached, escalate to on-call. | Irreversible (Process may be cycling) |
| **10** | **Container Restart Failure** | Docker daemon returns error (e.g. OOM, image corrupt, exit code $\ne 0$). | Returns `ActionExecutionResponse(status=FAILED, exit_code=1)`. | Recovery marked `failed`. Failure diagnostics saved. Incident transitions to `escalated`. | Irreversible (Container may be stopped) |
| **11** | **Application Health Check Failure** | Container restarts (`exit_code=0`), but `/health` returns 503 or times out. | Health prober returns `(is_healthy=False, status=503)`. | **CRITICAL:** Recovery execution marked `completed`, but verification marked `failed`. Incident transitions to `escalated`. | Irreversible (Container cycled, app still down) |
| **12** | **Database / Persistence Failure** | Database transaction fails while recording recovery result. | Agent execution receipt retained in agent's in-memory audit buffer. | Celery worker retries DB transaction with exponential backoff. Incident marked degraded until persisted. | N/A |
| **13** | **Duplicate Recovery Request** | Multiple concurrent requests dispatched for same incident. | Idempotency lock on `recovery_id` in Redis broker. | Second request rejected with HTTP 409 Conflict (`Action already executing`). | Reversible (Duplicate discarded) |

---

## 3. Operation Reversibility & Rollback Realism

### Non-Reversible Operations
- **`restart_container`:** Stopping and restarting an operating container process is **fundamentally irreversible**. Once the SIGTERM/SIGKILL signal is sent to PID 1 inside the container, prior ephemeral in-memory state, socket connections, and cache pools are destroyed. AutoHeal does **not** claim to provide an automatic rollback for container restarts.
- **Remediation on Restart Failure:** If restarting a container fails to restore application health, the system escalates to human on-call engineers rather than attempting blind recursive restarts that could exacerbate crash loops.

### Reversible / Bounded Operations
- **`scale_service`:** Adjusting replica count can be rolled back to the previous replica count if the new replicas fail health checks.
- **`rollback_deployment`:** Switching traffic to the prior container image tag is explicitly designed as a rollback operation.
