# AutoHeal DevOps — Statistical Anomaly Detection Engine

## Overview
The `AnomalyDetectionEngine` provides real-time time-series anomaly detection for DevOps and microservice metrics without relying on black-box external services.

## Detection Techniques

### 1. Rolling Z-Score Deviation
Calculates the statistical deviation of the latest sample against rolling baseline history:
$$z = \frac{x - \mu}{\sigma}$$
- If $|z| \ge 2.5$, the observation is flagged as an anomaly.
- Normalized anomaly score: $\min(1.0, |z| / 5.0)$.

### 2. Monotonic Growth / Memory Leak Detection
Specifically tailored for container memory heaps:
- Requires positive linear slope: $m > 0.5\%/\text{step}$.
- Requires high linear consistency: $R^2 > 0.70$.
- Requires current memory utilization: $> 50.0\%$.
- Prevents noise from small GC fluctuations while catching persistent heap leaks early.

### 3. Threshold Breaches
- **Critical Threshold**: Immediate assignment of `critical` severity when $x \ge \text{Threshold}_{critical}$ (e.g. CPU $\ge 90\%$, Memory $\ge 85\%$, Error Rate $\ge 5\%$).
- **Warning Threshold**: Assignment of `high` severity when $x \ge \text{Threshold}_{warning}$.

## Deduplication & Flapping Prevention
- **Deduplication Window**: An 15-minute suppression window checks for existing open anomalies on `(organization_id, service_id, metric_name)` before creating a new database record.
- **Minimum History Guardrail**: Requires a minimum of 3 observations to compute baseline statistics, preventing cold-start false positives.
