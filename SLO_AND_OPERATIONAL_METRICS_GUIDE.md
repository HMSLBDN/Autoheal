# AutoHeal DevOps — SLO & Operational Metrics Guide
**Target Audience**: Reliability Engineers, SRE Managers, Engineering Leadership  
**Scope**: Operational Reliability Scorecard, Service Level Objectives (SLOs), Measurement Provenance

---

## 1. Overview

AutoHeal provides a built-in Service Level Objective (SLO) engine that measures genuine operational efficiency across detection, alerting, human triage, autonomous remediation, and external delivery.

Every metric in the AutoHeal scorecard is tagged with explicit **data provenance**:
- `MEASURED`: Directly computed from genuine database timestamps and telemetry records.
- `CALCULATED`: Statistically derived from historical tenant performance baselines.
- `SYNTHETIC_DEMO`: Generated for sandbox evaluation and read-only demo environments.

---

## 2. Core Operational Metrics & Targets

| Metric Name | Slug | Target Threshold | Unit | Provenance | Description |
|---|---|:---:|:---:|:---:|---|
| **Service Availability** | `service_availability` | `>= 99.9%` | % | `MEASURED` | Average operational uptime across all monitored services in tenant. |
| **Mean Time to Acknowledge** | `mtta` | `<= 300s` (5 min) | s | `MEASURED` | Average seconds from breach detection to operator or automation acknowledgment. |
| **Mean Time to Resolve** | `mttr` | `<= 1800s` (30 min) | s | `MEASURED` | Average seconds from breach detection to post-recovery verification and closure. |
| **Recovery Verification Success Rate** | `recovery_verification_success_rate` | `>= 95.0%` | % | `MEASURED` | Percentage of executed recovery actions where post-recovery SLA health check passed. |
| **Failed Recovery Rate** | `failed_recovery_rate` | `<= 5.0%` | % | `MEASURED` | Percentage of remediations failing verification or triggering rollbacks. |
| **Incident Escalation Rate** | `escalation_rate` | `<= 10.0%` | % | `MEASURED` | Percentage of incidents requiring out-of-band escalation to human on-call. |
| **Incident Detection Latency** | `detection_latency` | `<= 60.0s` | s | `MEASURED` | Time between telemetry threshold breach and structured incident creation. |
| **Notification Delivery Reliability** | `notification_delivery_reliability` | `>= 99.0%` | % | `MEASURED` | Success rate of alerts delivered across configured Slack, Email, and Webhook channels. |

---

## 3. Compliance Scoring & Status Evaluation

Each metric evaluates into one of three operational states:
1. `compliant`: Current value satisfies target threshold with healthy margin.
2. `at_risk`: Metric is within 20% of breaching the target threshold.
3. `breached`: Current value violates SLA target threshold.

The overall organization reliability score (`overall_compliance_percent`) is computed as:
$$\text{Compliance \%} = \left( \frac{\text{Compliant Metrics Count}}{\text{Total Evaluated Metrics}} \right) \times 100$$

- `>= 85.0%` $\rightarrow$ `compliant` (Green)
- `60.0% - 84.9%` $\rightarrow$ `at_risk` (Yellow)
- `< 60.0%` $\rightarrow$ `breached` (Red)

---

## 4. API Reference

### Retrieve Complete Organization SLO Summary
```bash
curl "http://localhost:8000/api/v1/slo/summary?period=last_24h" \
  -H "Authorization: Bearer <OPERATOR_JWT_TOKEN>"
```

**Example Response**:
```json
{
  "organization_id": "24b0c732-38fa-46f6-93ef-cac38e47a64b",
  "period": "last_24h",
  "overall_compliance_percent": 87.5,
  "overall_status": "compliant",
  "metrics": [
    {
      "name": "Monitored Service Availability",
      "metric_key": "service_availability",
      "current_value": 99.98,
      "target_value": 99.9,
      "unit": "%",
      "status": "compliant",
      "source": "MEASURED",
      "sample_count": 5
    },
    {
      "name": "Mean Time to Acknowledge (MTTA)",
      "metric_key": "mtta",
      "current_value": 38.5,
      "target_value": 300.0,
      "unit": "s",
      "status": "compliant",
      "source": "MEASURED",
      "sample_count": 3
    },
    {
      "name": "Mean Time to Resolve (MTTR)",
      "metric_key": "mttr",
      "current_value": 242.0,
      "target_value": 1800.0,
      "unit": "s",
      "status": "compliant",
      "source": "MEASURED",
      "sample_count": 2
    },
    {
      "name": "Recovery Verification Success Rate",
      "metric_key": "recovery_verification_success_rate",
      "current_value": 97.4,
      "target_value": 95.0,
      "unit": "%",
      "status": "compliant",
      "source": "MEASURED",
      "sample_count": 38
    }
  ],
  "calculated_at": "2026-11-21T14:40:00Z"
}
```
