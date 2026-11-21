# AutoHeal DevOps — Canary Release & Rollback Decision Support Engine

## 1. Overview

Progressive rollouts and canary deployments limit the blast radius of software regressions. AutoHeal evaluates canary stage metrics (error rate, P95 latency, availability, CPU, memory) against baseline performance, identifying regressions before full production promotion.

---

## 2. Mandatory Production Safety Invariants

> [!IMPORTANT]
> **Strict Safety Guarantee**: All canary rollback recommendations formulated by AutoHeal are **strictly simulated and advisory**. Real production infrastructure is never modified, scaled, or rolled back automatically. Operators retain complete oversight and decision authority.

---

## 3. Evaluation Thresholds & Metrics

| Metric | Target | Default Threshold | Status Trigger |
|---|---|---|---|
| **Error Rate Delta** | $\le +0.5\%$ | $\Delta_{\text{error}} > 0.5\%$ | `breach` $\to$ `rollback_recommended` |
| **P95 Latency Delta** | $\le +100\text{ms}$ | $\Delta_{\text{latency}} > 100.0\text{ms}$ | `breach` $\to$ `rollback_recommended` |
| **Availability** | $\ge 99.9\%$ | $\text{Avail} < 99.9\%$ | `breach` $\to$ `rollback_recommended` |
| **CPU Utilization** | $\le 85.0\%$ | $\text{CPU} > 85.0\%$ | `warning` / `breach` |
| **Memory Utilization** | $\le 85.0\%$ | $\text{Mem} > 85.0\%$ | `warning` / `breach` |

---

## 4. Evaluation Stages & Decision Outcomes

The evaluator returns one of three advisory recommendations:

1. **`proceed`** (Stage: `progressive_rollout`, Status: `passed`):
   - All evaluated metrics are within safe operating limits.
   - Sample size satisfies minimum requirements ($\ge 3$ samples).
   - Advisory action: Promote canary traffic percentage to the next rollout phase (e.g., $10\% \to 25\% \to 50\%$).
2. **`pause`** (Stage: `canary`, Status: `degraded`):
   - Sample count is insufficient ($< 3$ observation windows) or metrics are borderline.
   - Advisory action: Pause promotion and gather additional telemetry before traffic shifts.
3. **`rollback_recommended`** (Stage: `rollback_recommended`, Status: `failed`):
   - One or more critical thresholds are breached.
   - Advisory action: Halt traffic promotion immediately and execute controlled rollback to the previous stable release.

---

## 5. API Reference

- `GET /api/v1/releases/evaluations`: List canary evaluation history.
- `POST /api/v1/releases/evaluate-canary`: Run canary telemetry evaluation.
- `GET /api/v1/releases/evaluations/{id}`: Detailed metric breakdown with baseline vs canary deltas.
