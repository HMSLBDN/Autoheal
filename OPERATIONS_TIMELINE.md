# AutoHeal DevOps — Unified Operations Timeline

## 1. Overview

Modern DevOps operations suffer from fragmented visibility: deployments live in CI/CD logs, alerts in Prometheus/Alertmanager, incidents in ticketing systems, and recoveries in automation logs. The Unified Operations Timeline (`GET /api/v1/timeline`) aggregates and orders all operational streams chronologically within an organization.

---

## 2. Aggregated Event Domains

The timeline merges events across 7 operational categories:

1. **`deployment`**: Release rollouts, canary traffic promotions, commit references.
2. **`alert`**: Raw threshold violations, metric spikes, Prometheus alert triggers.
3. **`incident`**: Formally declared incidents with severity, affected service, and error rates.
4. **`ai_diagnosis`**: Root cause analysis formulation, confidence scores, and correlated evidence.
5. **`recovery`**: Remediation actions proposed, approved, executed, and verified.
6. **`notification`**: Outbound dispatches to Slack, Teams, Email, or external webhooks.
7. **`escalation`**: Unacknowledged timeout escalations and manual tier advancements.

---

## 3. Data Schema

Each item in the timeline adheres to the unified `TimelineItemResponse` schema:

```json
{
  "id": "inc-INC-8874",
  "category": "incident",
  "title": "Incident Detected: Elevated Checkout 5xx Error Rate",
  "detail": "Status: investigating · Severity: critical · Error rate: 2.45%",
  "serviceName": "checkout-api",
  "severity": "critical",
  "status": "investigating",
  "timestamp": "2026-11-21T11:01:14Z",
  "metadata": {
    "error_rate": 2.45,
    "recovery_status": "Approval required"
  }
}
```

---

## 4. UI Representation

In the AutoHeal dashboard (`/dashboard/timeline`):
- Events are rendered as a vertical chronological stream.
- Category pills are color-coded (Deployments: Sky, Incidents: Crimson, AI: Violet, Recoveries: Teal, Notifications: Emerald, Escalations: Pink).
- Provides instant context during active triage, enabling operators to trace the exact chain of events leading up to any incident.
