# AutoHeal DevOps — AI Intelligence Architecture

## Overview
Phase 8 transforms the AutoHeal DevOps platform from a reactive alerting and remediation system into a proactive, predictive, and explainable site reliability engineering intelligence suite.

The architecture synthesizes mathematical statistics, time-series forecasting, machine learning evaluation, and large language model (LLM) diagnostics under strict security constraints.

```
+-----------------------------------------------------------------------------+
|                                Telemetry Bus                                |
|  (Prometheus, cAdvisor, Node Exporter, Host Agents, Application Events)     |
+-----------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------+
|                      Statistical Anomaly Detection Engine                   |
|   - Rolling Z-Score (z = (x - mean) / std)                                  |
|   - Exponentially Weighted Moving Average (EWMA)                            |
|   - Linear Least-Squares Trend & Monotonic Growth Rate (Slope & R^2)        |
+-----------------------------------------------------------------------------+
               |                                           |
               v                                           v
+-----------------------------+             +-----------------------------+
|  Predictive Horizon Engine  |             |  Service Health Risk Scorer |
|  - 15m, 30m, 60m Forecasts  |             |  - Explainable 0-100 Score  |
|  - Anomaly Probabilities    |             |  - Itemized Factor Weights  |
|  - Threshold Target Times   |             |  - Trend & Recovery Signals |
+-----------------------------+             +-----------------------------+
               |                                           |
               +---------------------+---------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|                       Cross-Incident & Context Bus                          |
|  - Historical Similarity (Tokenized Jaccard, Cosine, Past Mitigations)      |
|  - Root Cause Correlation Groups (Temporal, Shared Service, Cascades)       |
|  - Deployment Regression Intelligence (Pre- vs Post-Release Deltas)         |
+-----------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|                    Deep AI Incident Diagnosis Engine                        |
|  - Google Gemini 1.5 Pro SRE Provider (Bounded Timeout, Backoff Retries)    |
|  - Deterministic Rule-Based Heuristic Fallback Engine                       |
|  - Prompt Injection Filtering & Input Sanitization                          |
|  - Strict Recovery Action Allowlist Enforcement                             |
|  - Separation: Confirmed Telemetry Evidence vs Unverified Hypotheses        |
+-----------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|                   Human-in-the-Loop Operator Decision                       |
|  - Non-Executable Preventive Guidance                                       |
|  - Policy-Gated Remediation Approvals                                       |
+-----------------------------------------------------------------------------+
```

## Architectural Pillars
1. **Mathematical Rigor & Determinism**: Statistical tests (Z-score, EWMA, Linear Regression) filter noise and detect metric drift prior to alerting.
2. **Strict Advisory Boundaries**: AI generates advisory diagnostics and preventive suggestions only; it never directly triggers shell execution or bypasses the recovery policy engine.
3. **Multi-Tenant Isolation**: All queries, similarities, correlations, and predictive insights are strictly partitioned by `organization_id`.
4. **Transparent Evaluation**: All benchmarking against synthetic or test corpora is explicitly stamped `is_synthetic = True`.
