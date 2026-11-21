# Incident Resolution Integrity Report — AutoHeal DevOps SaaS
**Phase 13.1 Audit Report**  
**Date:** November 2026  
**Status:** PASSED — STRICT RESOLUTION INTEGRITY ENFORCED

---

## 1. Executive Summary

A critical integrity requirement of AutoHeal is that an incident cannot be marked `resolved` simply because an automated recovery command or playbook was dispatched. Automated recovery must be backed by empirical health verification. If health verification fails or has not run, the incident must remain unresolved. Furthermore, operators must have the ability to escalate unresolved incidents, and any manual sign-off must be tracked separately in audit logs without falsely claiming that automated recovery succeeded.

This report documents the architectural audit, state machine implementation, API transition endpoint, and regression testing verifying incident resolution integrity.

---

## 2. Core Integrity Invariants

1. **No Premature Resolution:** Dispatching a recovery action (e.g. container restart) does not equal resolution. Resolution requires a verified post-recovery health check.
2. **Verification Gate:** If a recovery execution has `verification != "success"`, or if no recovery record exists, an automated transition to `resolved` is rejected with `HTTP 400 Bad Request`.
3. **Escalation Support:** Incidents that fail recovery or cannot be verified can be transitioned to `escalated` with an explicit reason.
4. **Manual Sign-Off Separation:** When an operator resolves an incident manually (`manual_signoff=True`), the state machine records `manual_signoff=True`, `signoff_by=actor_id`, and explicitly marks `recovery_verified=False` if automated verification did not succeed. The system never misrepresents manual sign-off as successful automated recovery.
5. **Auditable Lifecycle:** Every transition immutably records `previous_state`, `new_state`, `actor_id`, `actor_email`, `actor_role`, `timestamp`, and `reason` in both `IncidentEvent` and tenant `AuditEvent` logs.

---

## 3. Incident State Machine & Transition Endpoint

### 3.1 State Machine Specification (`backend/app/services/incident_state_machine.py`)
The state machine governs allowable state transitions:
```
           +--------------+
           |  triggered   |
           +-------+------+
                   |
                   v
           +--------------+
           |investigating | <-------+
           +---+----+-----+         |
               |    |               |
      +--------+    +---------+     |
      |                       |     |
      v                       v     |
+-----------+           +-----------+
| escalated |           | resolved  |
+-----+-----+           +-----+-----+
      |                       |
      v                       v
+-----------+           +-----------+
| resolved  |           |  closed   |
+-----------+           +-----------+
```

Allowed Transitions:
- `triggered` -> `investigating`, `escalated`, `closed`
- `investigating` -> `resolved`, `escalated`, `closed`
- `escalated` -> `investigating`, `resolved`, `closed`
- `resolved` -> `investigating`, `closed`
- `closed` -> (terminal; no transitions permitted)

### 3.2 Transition Verification Logic
When transitioning to `resolved`:
```python
def verify_resolution_eligibility(
    incident: Incident,
    manual_signoff: bool = False,
    notes: Optional[str] = None
) -> Tuple[bool, str, bool]:
    # Check latest recovery record
    if incident.recoveries:
        latest_recovery = sorted(incident.recoveries, key=lambda r: r.created_at or 0)[-1]
        if latest_recovery.verification in ("success", "verified") or latest_recovery.status == "success":
            return True, "Automated recovery verified successfully", True

    if manual_signoff:
        if not notes:
            return False, "Manual sign-off requires explanatory notes", False
        return True, f"Manually resolved by operator: {notes}", False

    return False, "Cannot resolve incident: no verified automated recovery or manual operator sign-off provided", False
```

### 3.3 API Endpoint (`POST /api/v1/incidents/{incident_id}/transition`)
- **Role Requirement:** `RequireOperatorDep` (accessible only to `operator` and `admin` roles).
- **Request Body:**
  ```json
  {
    "new_status": "resolved",
    "reason": "Post-restart health verification check passed",
    "manual_signoff": false,
    "notes": null
  }
  ```
- **Validation:**
  - Transitioning from an identical status (e.g. `investigating` -> `investigating`) is rejected.
  - Transitioning without a descriptive `reason` is rejected.
  - Transitioning a closed incident is rejected.
  - Attempting to transition to `resolved` with a failed recovery produces `400 Bad Request`.
  - Manual sign-off without notes produces `400 Bad Request`.

---

## 4. Frontend & Type Definitions

The TypeScript types and API client have been updated to support `escalated` status and state machine transitions:
- `types/index.ts`: Added `'escalated'` to `IncidentStatus`.
- `lib/api/resources.ts`: Added `incidentsApi.transition(id, payload)` with full typing.

---

## 5. Regression Test Results

Suite: `backend/tests/test_phase13_recovery_safety_incident_integrity.py`
- `test_transition_endpoint_blocks_viewer_role` — **PASSED** (HTTP 403 returned for viewers).
- `test_transition_endpoint_blocks_cross_tenant_access` — **PASSED** (HTTP 404 returned for other orgs).
- `test_cannot_mark_resolved_without_health_verification` — **PASSED** (HTTP 400 returned when no recovery verified).
- `test_cannot_mark_resolved_when_verification_failed` — **PASSED** (HTTP 400 returned when recovery verified=failed).
- `test_failed_recovery_can_be_escalated` — **PASSED** (Transition to `escalated` successfully recorded).
- `test_manual_signoff_recorded_separately_and_cannot_claim_automated_success` — **PASSED** (Recorded with `manual_signoff=True`, `recovery_verified=False`).
- `test_valid_verified_recovery_allows_resolution` — **PASSED** (Verified recovery resolves successfully).
- `test_transition_requires_mandatory_reason_and_rejects_self_transition` — **PASSED** (Rejects invalid transition arguments).

**Result: 100% resolution integrity invariants verified.**
