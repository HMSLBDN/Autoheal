# AutoHeal DevOps — Preventive Recommendation Guidance

## Overview
Preventive recommendations represent proactive, non-executable advisory interventions formulated by AutoHeal to avert system failures before metrics cross hard alerting thresholds.

## Categorization & Playbooks

### 1. Memory Leak Mitigation (`memory_leak`)
- **Trigger**: Monotonic positive slope ($m > 0.5\%/\text{step}$, $R^2 > 0.70$) on `memory_percent`.
- **Expected Benefit**: Prevents unplanned container termination by Linux OOM killer (`OOMKilled`) and connection drops.
- **Suggested Action**: Inspect heap allocations, review recent database connection pool pool size, or schedule a graceful service restart during a low-traffic window.

### 2. Pre-emptive Capacity Scaling (`capacity_growth`)
- **Trigger**: Linear / EWMA projection indicates `cpu_percent` or `request_rate` will breach 85% within the 30-minute horizon.
- **Expected Benefit**: Prevents request queueing, elevated P95 latency, and upstream gateway HTTP 504 timeouts.
- **Suggested Action**: Increase deployment replica count proactively or adjust Kubernetes Horizontal Pod Autoscaler (HPA) minimum replica settings.

### 3. Recovery Flapping Policy Audit (`flapping_policy`)
- **Trigger**: Service experiences repeated failed automated recoveries ($\ge 2$) or $\ge 3$ incident triggers within 7 days.
- **Expected Benefit**: Reduces on-call fatigue, avoids recovery retry storms, and identifies root architectural defects.
- **Suggested Action**: Audit crash logs for non-restartable errors (e.g. database schema mismatch or missing environment secrets).

## Status Lifecycle
1. `open`: Freshly generated recommendation awaiting operator evaluation.
2. `acknowledged`: SRE team has reviewed the suggestion and assigned it to an engineering queue.
3. `applied`: The preventive change (e.g. replica count increased, memory leak patched) has been committed.
4. `dismissed`: Operator determined the warning was nominal or non-actionable.
