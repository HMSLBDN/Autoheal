# AutoHeal DevOps — Escalation Policy & Alerting Guide

## 1. Overview

Escalation policies guarantee that critical incidents receive timely operator attention. When an incident remains unacknowledged beyond configured timeout thresholds, AutoHeal automatically escalates to higher operational tiers, alerts secondary channels, and logs auditable escalation events.

---

## 2. Policy Configuration Model

An `EscalationPolicy` defines:
- **Severity Trigger**: `critical`, `high`, `medium`, or `low`.
- **Unacknowledged Timeout**: Duration in minutes before the initial escalation fires (e.g. 15 minutes).
- **Max Escalation Level**: Maximum tier allowed (1 to 5).
- **Multi-Level Rules**: Staged hierarchy specifying target channels and roles per level.
- **Quiet Hours**: Time window (UTC) during which non-critical alerts are suppressed.

### Example Policy JSON
```json
{
  "name": "Production Critical Tier-1 Escalation",
  "severity": "critical",
  "unacknowledgedTimeoutMinutes": 15,
  "maxEscalationLevel": 3,
  "rules": [
    {
      "level": 1,
      "timeoutMinutes": 15,
      "channelIds": ["chan-slack-primary"],
      "targetRoles": ["operator"]
    },
    {
      "level": 2,
      "timeoutMinutes": 30,
      "channelIds": ["chan-pagerduty-oncall"],
      "targetRoles": ["admin", "sre-lead"]
    },
    {
      "level": 3,
      "timeoutMinutes": 45,
      "channelIds": ["chan-exec-digest"],
      "targetRoles": ["admin"]
    }
  ],
  "quietHoursEnabled": true,
  "quietHoursStartUtc": "22:00",
  "quietHoursEndUtc": "06:00",
  "isActive": true
}
```

---

## 3. Escalation Evaluation Engine

The engine evaluates open incidents on a scheduled cadence (every 60 seconds via Celery Beat or on-demand via `POST /api/v1/escalations/evaluate`):
1. **Filter**: Queries open incidents matching the policy severity within the tenant organization.
2. **Elapsed Calculation**:
   $$\text{ElapsedMinutes} = \frac{\text{Now} - \text{DetectedAt}}{60}$$
3. **Threshold Check**: If $\text{ElapsedMinutes} \ge \text{TimeoutMinutes}$ and the current level is below `max_escalation_level`:
   - Increments escalation level ($\text{Level} \leftarrow \text{CurrentLevel} + 1$).
   - Creates an `EscalationEvent` record.
   - Appends an escalation timeline note to `IncidentComment`.
   - Dispatches priority notification alerts with `event_type="incident_escalated"`.

---

## 4. Quiet Hours Suppression

Quiet hours allow organizations to avoid paging off-duty engineers during overnight windows:
- **Window Evaluation**: Handles overnight intervals that span midnight UTC (e.g., `22:00` to `06:00`).
- **Critical Incident Override**: Critical severity incidents continue to generate dashboard alerts and audit logs, ensuring visibility even during quiet hours.
