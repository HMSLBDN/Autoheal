# AutoHeal DevOps — Incident Communication & Collaboration Workflow

## 1. Overview

Effective incident response requires transparent communication, clear ownership, and non-repudiable audit logs. The Incident Collaboration subsystem provides public discussion threads, internal triage notes, owner assignments, and alert acknowledgment workflows directly integrated into the incident timeline.

---

## 2. Communication Entry Types

Every communication entry attached to an incident is stored in `IncidentComment` and categorized into one of five distinct types:

1. `comment`: Public operator note visible across team dashboards and exported in post-mortem reports.
2. `internal_note`: Sensitive triage notes (e.g., token rotations, private credentials, internal tickets) visible only to authenticated internal operators.
3. `status_change`: Automated audit records generated when incident status or recovery status transitions.
4. `escalation`: Escalation records logging when timeout thresholds are crossed or manual escalation occurs.
5. `resolution_summary`: Final post-incident summary describing root cause, resolution actions, and preventive measures.

---

## 3. Incident Acknowledgment Workflow

1. **Trigger**: An on-call operator reviews an active incident and clicks **"Acknowledge Alert"** or issues `POST /api/v1/incidents/{incident_id}/acknowledge`.
2. **State Transition**:
   - `incident.status` transitions from `open` to `investigating`.
   - `incident.recovery_status` records `Acknowledged by <OperatorName>`.
3. **Escalation Silence**: The automated timeout escalation scanner checks `incident.status == "open"`. Once an incident is acknowledged (`investigating`), escalation timeout timers are paused, preventing unnecessary secondary alerts.
4. **Timeline Entry**: A `status_change` comment is posted to the communication thread:
   `"Incident acknowledged by Alex Chen. Active investigation in progress."`

---

## 4. Ownership Assignment

Operators can claim or reassign incidents via `POST /api/v1/incidents/{incident_id}/assign`:
- **Active Ownership**: Previous active assignments for that incident are deactivated (`is_active=False`).
- **Audit Tracking**: Records `assigned_to_name`, `assigned_by_name`, and exact timestamp.
- **UI Indication**: The Incident Details view immediately surfaces the active owner pill (`Owner: Alex Chen`).

---

## 5. API Reference

| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/v1/incidents/{id}/comments` | `GET` | Viewer+ | Retrieve full chronological discussion thread |
| `/api/v1/incidents/{id}/comments` | `POST` | Operator+ | Post public comment or internal note |
| `/api/v1/incidents/{id}/assignment` | `GET` | Viewer+ | Inspect current assigned owner |
| `/api/v1/incidents/{id}/assign` | `POST` | Operator+ | Assign ownership to operator |
| `/api/v1/incidents/{id}/acknowledge` | `POST` | Operator+ | Acknowledge alert and halt escalation timer |
| `/api/v1/incidents/{id}/escalate` | `POST` | Operator+ | Manually advance escalation level |
