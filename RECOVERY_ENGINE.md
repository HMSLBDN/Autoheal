# AutoHeal DevOps — Recovery Engine & Remediation Architecture

This document describes the policy-governed remediation engine, restricted infrastructure agent boundary, simulation mode, and human-in-the-loop approval workflow.

---

## 1. Remediation Philosophy & Safety Boundary

AutoHeal DevOps operates on a **zero-unrestricted-execution** principle. The recovery engine does **not** allow arbitrary shell command execution, remote script injection, or Docker socket mounting.

Instead, remediation is modeled as an enumerated set of declarative operations with strict parameter bounds, validated by an action allowlist and gated by Role-Based Access Control (RBAC).

---

## 2. Action Allowlist & Parameter Bounds

All remediation actions recommended by AI or heuristics must pass validation against `RecoveryActionType` in `app.services.agent`:

| Action Type | Allowed Parameters | Parameter Bounds / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `restart_service` | `grace_period_seconds` | Integer: 0 to 60 seconds | Triggers a graceful service process/container restart |
| `scale_service` | `replicas` | Integer: 1 to 10 replicas | Horizontally scales service replica count within strict bounds |
| `rollback_deployment` | `target_version`, `previous_release_tag` | Alphanumeric version string (e.g., `v1.2.3`) | Rolls back service to previous stable release tag |
| `clear_cache` | `cache_prefix`, `partition` | Allowlisted prefixes (e.g., `session:*`, `query:*`) | Invalidates stale or corrupted cache partitions |

### Strict Disallowance
The following are unconditionally blocked and rejected:
- Arbitrary bash/powershell strings (`exec`, `system`, `sh`, `cmd.exe`).
- File deletion commands (`rm -rf`, `del`).
- Network configuration alteration or credential extraction.
- Exceeding maximum replica counts (> 10) or invalid version tags.

---

## 3. Safe Simulation Mode (`RECOVERY_SIMULATION_MODE=true`)

By default and across all development/testing environments, AutoHeal runs in **Safe Simulation Mode**:

- Configured via: `RECOVERY_SIMULATION_MODE=true` in `app.config.Settings`.
- Execution is dispatched to `SimulatedAgentClient` (`app.services.agent`):
  * Emulates realistic container execution latency (100–300ms).
  * Simulates standard output and standard error logs.
  * Returns realistic exit code `0` for success or mock error states for fault testing.
  * Computes an authentic SHA-256 cryptographic evidence receipt.
- **Guarantee**: No real host files, Docker containers, Kubernetes pods, or cloud instances are altered while in simulation mode.

---

## 4. Cryptographic Execution Envelopes & Receipts

When communicating with an execution agent (or running in simulation):

### 4.1 Cryptographic Request Envelope
1. **Nonce Generation**: Single-use UUIDv4 nonce generated per execution request.
2. **Replay Defense**: Control plane tracks consumed nonces in cache/database; duplicate nonces are immediately rejected.
3. **Timestamp Drift Protection**: Requests with timestamps diverging by more than 300 seconds from UTC are rejected.
4. **HMAC Signature**: The envelope payload is signed with `AGENT_SECRET_KEY` using HMAC-SHA256 (`sign_payload`).

### 4.2 Cryptographic Execution Receipt
Upon completion, the agent returns an immutable execution receipt:
```json
{
  "action_id": "rec-550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "exit_code": 0,
  "duration_ms": 245.8,
  "stdout_summary": "Service web-frontend container gracefully restarted (grace_period=10s)",
  "stderr_summary": "",
  "receipt_hash": "a8f5c9e2b4d1a3c7...64-char-sha256-hex",
  "completed_at": "2026-11-21T11:00:00.000Z"
}
```

---

## 5. Human-in-the-Loop RBAC Approval Workflow

Remediation actions require authorized operator approval prior to execution:

```
[ AI Diagnosis Proposes RecoveryAction (status: PENDING_APPROVAL) ]
                                |
                                v
     [ SSE Broadcast: recovery.proposed -> Frontend Notification ]
                                |
                                v
               [ Operator / Admin Reviews Action ]
               +---------------------------------+
               | Action: restart_service         |
               | Target: checkout-service        |
               | Confidence: 94%                 |
               | Rationale: Memory leak detected |
               +---------------------------------+
                                |
                     POST /api/v1/recoveries/{id}/approve
                     (RBAC check: role in ['admin', 'operator'])
                                |
             +------------------+------------------+
             |                                     |
     [ Operator Approves ]                 [ Operator Rejects ]
             |                                     |
             v                                     v
  Status: APPROVED / IN_PROGRESS        Status: REJECTED
  Celery task dispatched                Incident marked unmitigated
             |                                     |
             v                                     v
  [ Safe Simulation Execution ]          Audit Log & Escalation
             |
             v
  [ Post-Recovery Health Probe ]
             |
   +---------+---------+
   |                   |
[ Healthy ]       [ Unhealthy ]
   |                   |
   v                   v
Incident: RESOLVED   Escalate / Page On-Call
```

### RBAC Role Matrix:
- `admin`: Can propose, approve, reject, execute, or cancel any recovery action.
- `operator`: Can approve, reject, or execute recommended recovery actions.
- `viewer`: Read-only access; attempts to approve return `HTTP 403 Forbidden`.

---

## 6. Cooldowns & Flap Prevention

To prevent remediation loops and cascading restarts:
- **`RECOVERY_COOLDOWN_SECONDS`**: Minimum duration (default: 300 seconds) required between successive recovery actions on the same service.
- **`MAX_RECOVERY_RETRIES`**: Upper limit (default: 3 attempts) of automated recovery attempts per incident. If retries are exhausted without health restoration, the incident is flagged for manual senior escalation.

---

## 7. Post-Recovery Verification

Following recovery execution:
1. The engine enters verification state for a configurable observation window (default: 30–60 seconds).
2. Deep service health probes (`/health`) and metrics scraping (`/metrics`) query the service.
3. If error rates drop below threshold and liveness probes succeed:
   - Incident state transitions to `resolved`.
   - Resolution timestamp and MTTR (Mean Time to Resolution) are logged.
   - An event is broadcast over SSE to update the operator dashboard in real time.
4. If the service remains degraded:
   - Escalation alert is triggered.
   - Secondary remediation is prohibited if cooldown is active.
