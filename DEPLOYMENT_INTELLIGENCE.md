# AutoHeal DevOps — Deployment Intelligence & Correlation

## 1. Overview

Deployments are among the most frequent catalysts for operational incidents. AutoHeal's Deployment Intelligence Engine tracks software releases, maps temporal proximity to incident onset, and analyzes telemetry deltas without making unsupported causation claims.

---

## 2. Temporal Correlation Methodology

When an incident is detected on a monitored service:
1. **Window Query**: The engine searches for `DeploymentEvent` records on the service within a 60-minute lookback window prior to incident detection.
2. **Delta Extraction**: Compares telemetry metrics from the 15-minute window immediately preceding the deployment against metrics observed following the deployment:
   - Error rate delta: $\Delta_{\text{error}} = \text{ErrorRate}_{\text{post}} - \text{ErrorRate}_{\text{pre}}$
   - Latency delta: $\Delta_{\text{latency}} = \text{LatencyMs}_{\text{post}} - \text{LatencyMs}_{\text{pre}}$
   - Availability delta: $\Delta_{\text{avail}} = \text{Avail}_{\text{post}} - \text{Avail}_{\text{pre}}$
3. **Correlation vs Causation Guardrail**:
   - Correlation is established when an incident occurs within minutes of a release deployment exhibiting elevated error rates.
   - The engine explicitly labels findings as **correlated hypotheses** (`probableImpactSummary`).
   - It **never** asserts definitive causation without confirming application log evidence or dependency timeout signatures.

---

## 3. Data Representation

```json
{
  "serviceId": "svc-checkout",
  "serviceName": "checkout-api",
  "releaseTag": "release-2026.11.08.3",
  "deployedAt": "2026-11-21T09:34:06Z",
  "timeSinceDeploymentMinutes": 8,
  "isTemporallyCorrelated": true,
  "preDeploymentMetrics": {
    "error_rate": 0.05,
    "latency_ms": 142.0
  },
  "postDeploymentMetrics": {
    "error_rate": 1.84,
    "latency_ms": 684.0
  },
  "metricDeltas": {
    "error_rate": 1.79,
    "latency_ms": 542.0
  },
  "probableImpactSummary": "Deployment completed 8 minutes before error rate threshold breach.",
  "recommendedInvestigation": "Inspect upstream payment gateway timeout logs and evaluate canary rollback."
}
```

---

## 4. Operational Value

- Accelerates triage by pinpointing suspect releases immediately upon alert firing.
- Informs canary release decisions and automated rollback recommendations.
- Feeds into post-mortem incident reports with pre- and post-deployment performance graphs.
