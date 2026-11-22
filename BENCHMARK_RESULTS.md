# AUTOHEAL DEVOPS — BENCHMARK RESULTS & EMPIRICAL EVIDENCE
## Phase 14: Systematic Evaluation Across 8 Deterministic Scenarios

---

## 1. Executive Summary

This document presents empirical benchmark evaluation results gathered across all 8 standardized evaluation scenarios in AutoHeal DevOps.

Each scenario was evaluated across multiple seed-isolated runs ($N=5$, base seed $42$, seeds $43$ to $47$) to establish rigorous statistical distributions.

### Primary Research Finding:
> Autonomous self-healing in AutoHeal DevOps achieved an **88.7% to 92.4% reduction in mean outage duration** compared to the unmitigated 60-second benchmark observation ceiling under identical deterministic fault conditions ($N=5$ matched seed pairs), while maintaining **100.0% safety compliance and 0.0% false-positive rates**.

---

## 2. Comparative Benchmark Matrix (Recovery Enabled vs Control)

| Scenario ID & Name | Recovery Enabled Mean MTTR | Control Baseline (60s Observation Window Cutoff) | Outage Reduction ($\Delta T$) | Outage Reduction (%) | Statistical Qualification & Significance | Evidence Tier |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **S1: Healthy Baseline** | $0.0 \pm 0.0\,ms$ | $0.0 \pm 0.0\,ms$ | $0.0\,ms$ | Baseline | N/A (Zero-variance baseline) | `SYNTHETIC` |
| **S2: 503 Outage** | $5,153.6 \pm 461.4\,ms$ | $60,000.0 \pm 0.0\,ms$* | **$54,846.4\,ms$** | **$91.4\%$** | Descriptive ($\Delta T > 2 \times SE$, paired $SE = 206.4\,ms$) | `SIMULATED` |
| **S3: High Error Rate** | $4,536.8 \pm 426.7\,ms$ | $60,000.0 \pm 0.0\,ms$* | **$55,463.2\,ms$** | **$92.4\%$** | Descriptive ($\Delta T > 2 \times SE$, paired $SE = 190.8\,ms$) | `SIMULATED` |
| **S4: Resource Exhaustion** | $6,798.8 \pm 552.4\,ms$ | $60,000.0 \pm 0.0\,ms$* | **$53,201.2\,ms$** | **$88.7\%$** | Descriptive ($\Delta T > 2 \times SE$, paired $SE = 247.0\,ms$) | `SIMULATED` |
| **S5: Repeated Alerts** | $4,564.4 \pm 433.9\,ms$ | $60,000.0 \pm 0.0\,ms$* | **$55,435.6\,ms$** | **$92.4\%$** | Descriptive ($\Delta T > 2 \times SE$, paired $SE = 194.1\,ms$) | `SIMULATED` |
| **S6: Verification Failure** | $60,000.0 \pm 0.0\,ms$* (Escalated) | $60,000.0 \pm 0.0\,ms$* | $0.0\,ms$ | Escalation Gate | 100% Escalated to Human On-Call | `SIMULATED` |
| **S7: Unauthorized Recovery**| Blocked (HTTP 403) | N/A | Security Gate | 100% RBAC Gate | Zero Mutation Allowed | `SIMULATED` |
| **S8: Unapproved Recovery** | Held in Pending | N/A | Sign-off Gate | 100% Policy Gate| Awaiting Human Approval Token | `SIMULATED` |

*\* Note: The control baseline of $60,000.0\,ms$ is an assigned observation window timeout (right-censored bound), not an observed natural resolution. See Section 4 for scientific qualification.*

---

### The Additive Outage Duration Model:
In all scenarios with autonomous remediation enabled, total outage duration is computed as the exact wall-clock span from fault injection to health restoration:
$$T_{\text{outage}} = (t_{\text{restored}} - t_{\text{fault}}) = T_{\text{detect}} + T_{\text{dispatch}} + T_{\text{recovery}} + T_{\text{verify}}$$
where:
1. **$T_{\text{detect}}$:** Detection latency from fault injection to platform anomaly detection.
2. **$T_{\text{dispatch}}$:** Recovery initiation & policy evaluation dispatch delay ($200.0\,ms$ in standard scenarios, $250.0\,ms$ in flapping suppression).
3. **$T_{\text{recovery}}$:** Remediation execution duration (simulated process restart, worker pool reload, or replica scaling).
4. **$T_{\text{verify}}$:** Post-recovery readiness and health check verification delay ($800.0\,ms$ for S2; $600.0\,ms$ for S3; $1,000.0\,ms$ for S4).

---

## 3. Detailed Scenario Breakdowns (Base Seed: 42, N = 5)

### Scenario 1: Healthy Baseline (`healthy_baseline`)
- **Sample Size:** $N = 5$ (Seeds 43 to 47)
- **Mean Detection Latency:** $0.0 \pm 0.0\,ms$
- **False-Positive Rate:** $0.0\%$ (0 false alarms triggered across all trials)
- **Safety Compliance Rate:** $100.0\%$
- **Total Outage Duration:** $0.0 \pm 0.0\,ms$
- **Evidence Classification:** `SYNTHETIC`

### Scenario 2: Service Unavailable Outage (`service_unavailable`)
- **Simulated Failure Condition:** Hard HTTP 503 outage / container crash (Simulated)
- **Simulated Recovery Action:** `restart_container` (Simulated cold container reboot lifecycle)
- **Sample Size:** $N = 5$ matched seed pairs
- **Additive Components ($ms$):**
  - Detection Latency ($T_{\text{detect}}$): Min: $1,234.7$ · Max: $1,999.4$ · Mean: $1,552.6 \pm 280.1$ · Median: $1,516.7$
  - Dispatch Overhead ($T_{\text{dispatch}}$): Fixed $200.0 \pm 0.0$ (Policy evaluation, allowlist matching, task scheduling)
  - Recovery Duration ($T_{\text{recovery}}$): Min: $2,298.3$ · Max: $2,906.3$ · Mean: $2,601.0 \pm 246.5$ · Median: $2,643.9$
  - Verification Probe Delay ($T_{\text{verify}}$): Fixed $800.0 \pm 0.0$ (/healthz readiness probe delay)

**Raw Run Additive Breakdown (S2):**

| Run | Seed | $T_{\text{detect}}$ ($ms$) | $T_{\text{dispatch}}$ ($ms$) | $T_{\text{recovery}}$ ($ms$) | $T_{\text{verify}}$ ($ms$) | Total Outage $T_{\text{outage}}$ ($ms$) | Action Executed | Outcome |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | 43 | 1,234.7 | 200.0 | 2,643.9 | 800.0 | **4,878.6** | `restart_container` | Restored / Verified |
| 2 | 44 | 1,567.7 | 200.0 | 2,412.0 | 800.0 | **4,979.7** | `restart_container` | Restored / Verified |
| 3 | 45 | 1,444.7 | 200.0 | 2,298.3 | 800.0 | **4,743.0** | `restart_container` | Restored / Verified |
| 4 | 46 | 1,999.4 | 200.0 | 2,906.3 | 800.0 | **5,905.7** | `restart_container` | Restored / Verified |
| 5 | 47 | 1,516.7 | 200.0 | 2,744.4 | 800.0 | **5,261.1** | `restart_container` | Restored / Verified |
| **Mean** | — | **1,552.6** | **200.0** | **2,601.0** | **800.0** | **5,153.6** | — | — |

- **Total Outage Duration Distribution:**
  - Recovery Enabled: Min: $4,743.0\,ms$ · Max: $5,905.7\,ms$ · Mean: **$5,153.6\,ms$** · Median: $4,979.7\,ms$ · $P_{95} = 5,905.7\,ms$ · $\sigma = \pm 461.4\,ms$
  - Control Baseline: $60,000.0 \pm 0.0\,ms$ (Right-censored observation ceiling)
- **Net Improvement:** **$91.4\%$ Outage Reduction** ($54,846.4\,ms$ saved relative to the 60s observation window; paired $SE = 206.4\,ms$).
- **Evidence Classification:** `SIMULATED` / `CALCULATED`

### Scenario 3: High Error Rate Surge (`high_error_rate`)
- **Simulated Failure Condition:** Elevated 500 error rate (22%) (Simulated)
- **Simulated Recovery Action:** `restart_pool` (Simulated in-place worker pool recycling & process reload)
- **Sample Size:** $N = 5$ matched seed pairs
- **Additive Components ($ms$):**
  - Detection Latency ($T_{\text{detect}}$): Min: $1,584.7$ · Max: $2,349.4$ · Mean: $1,902.6 \pm 280.1$ · Median: $1,866.7$
  - Dispatch Overhead ($T_{\text{dispatch}}$): Fixed $200.0 \pm 0.0$ (Policy evaluation, allowlist matching, task scheduling)
  - Recovery Duration ($T_{\text{recovery}}$): Min: $1,581.9$ · Max: $2,088.6$ · Mean: $1,834.2 \pm 205.4$ · Median: $1,869.9$
  - Verification Probe Delay ($T_{\text{verify}}$): Fixed $600.0 \pm 0.0$ (Warm health check)

**Raw Run Additive Breakdown (S3):**

| Run | Seed | $T_{\text{detect}}$ ($ms$) | $T_{\text{dispatch}}$ ($ms$) | $T_{\text{recovery}}$ ($ms$) | $T_{\text{verify}}$ ($ms$) | Total Outage $T_{\text{outage}}$ ($ms$) | Action Executed | Outcome |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | 43 | 1,584.7 | 200.0 | 1,869.9 | 600.0 | **4,254.6** | `restart_pool` | Restored / Verified |
| 2 | 44 | 1,917.7 | 200.0 | 1,676.7 | 600.0 | **4,394.4** | `restart_pool` | Restored / Verified |
| 3 | 45 | 1,794.7 | 200.0 | 1,581.9 | 600.0 | **4,176.6** | `restart_pool` | Restored / Verified |
| 4 | 46 | 2,349.4 | 200.0 | 2,088.6 | 600.0 | **5,238.0** | `restart_pool` | Restored / Verified |
| 5 | 47 | 1,866.7 | 200.0 | 1,953.7 | 600.0 | **4,620.4** | `restart_pool` | Restored / Verified |
| **Mean** | — | **1,902.6** | **200.0** | **1,834.2** | **600.0** | **4,536.8** | — | — |

- **Total Outage Duration Distribution:**
  - Recovery Enabled: Min: $4,176.6\,ms$ · Max: $5,238.0\,ms$ · Mean: **$4,536.8\,ms$** · Median: $4,394.4\,ms$ · $P_{95} = 5,238.0\,ms$ · $\sigma = \pm 426.7\,ms$
  - Control Baseline: $60,000.0 \pm 0.0\,ms$ (Right-censored observation ceiling)
- **Net Improvement:** **$92.4\%$ Outage Reduction** ($55,463.2\,ms$ saved relative to the 60s observation window; paired $SE = 190.8\,ms$).
- **Evidence Classification:** `SIMULATED` / `CALCULATED`

### Scenario 4: Resource Exhaustion (`resource_exhaustion`)
- **Simulated Failure Condition:** CPU & Memory Saturation (> 90%) (Simulated)
- **Simulated Recovery Action:** `scale_service` (Simulated horizontal pod replica scaling & quota expansion)
- **Sample Size:** $N = 5$ matched seed pairs
- **Additive Components ($ms$):**
  - Detection Latency ($T_{\text{detect}}$): Min: $2,142.4$ · Max: $3,077.1$ · Mean: $2,531.0 \pm 342.4$ · Median: $2,487.0$
  - Dispatch Overhead ($T_{\text{dispatch}}$): Fixed $200.0 \pm 0.0$ (Policy evaluation, allowlist matching, task scheduling)
  - Recovery Duration ($T_{\text{recovery}}$): Min: $2,714.6$ · Max: $3,424.1$ · Mean: $3,067.8 \pm 287.6$ · Median: $3,117.8$
  - Verification Probe Delay ($T_{\text{verify}}$): Fixed $1,000.0 \pm 0.0$ (Capacity settling & shedding delay)

**Raw Run Additive Breakdown (S4):**

| Run | Seed | $T_{\text{detect}}$ ($ms$) | $T_{\text{dispatch}}$ ($ms$) | $T_{\text{recovery}}$ ($ms$) | $T_{\text{verify}}$ ($ms$) | Total Outage $T_{\text{outage}}$ ($ms$) | Action Executed | Outcome |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | 43 | 2,142.4 | 200.0 | 3,117.8 | 1,000.0 | **6,460.2** | `scale_service` | Restored / Verified |
| 2 | 44 | 2,549.4 | 200.0 | 2,847.3 | 1,000.0 | **6,596.7** | `scale_service` | Restored / Verified |
| 3 | 45 | 2,399.1 | 200.0 | 2,714.6 | 1,000.0 | **6,313.7** | `scale_service` | Restored / Verified |
| 4 | 46 | 3,077.1 | 200.0 | 3,424.1 | 1,000.0 | **7,701.2** | `scale_service` | Restored / Verified |
| 5 | 47 | 2,487.0 | 200.0 | 3,235.1 | 1,000.0 | **6,922.1** | `scale_service` | Restored / Verified |
| **Mean** | — | **2,531.0** | **200.0** | **3,067.8** | **1,000.0** | **6,798.8** | — | — |

- **Total Outage Duration Distribution:**
  - Recovery Enabled: Min: $6,313.7\,ms$ · Max: $7,701.2\,ms$ · Mean: **$6,798.8\,ms$** · Median: $6,596.7\,ms$ · $P_{95} = 7,701.2\,ms$ · $\sigma = \pm 552.4\,ms$
  - Control Baseline: $60,000.0 \pm 0.0\,ms$ (Right-censored observation ceiling)
- **Net Improvement:** **$88.7\%$ Outage Reduction** ($53,201.2\,ms$ saved relative to the 60s observation window; paired $SE = 247.0\,ms$).
- **Evidence Classification:** `SIMULATED` / `CALCULATED`
- **Total Outage Duration:**
  - Recovery Enabled: Min: $6,313.7\,ms$ · Max: $7,701.2\,ms$ · Mean: **$6,798.8\,ms$** · Median: $6,596.7\,ms$ · $P_{95} = 7,701.2\,ms$ · $\sigma = \pm 552.4\,ms$
  - Control Baseline: $60,000.0 \pm 0.0\,ms$ (Right-censored observation ceiling)
- **Net Improvement:** **$88.7\%$ Outage Reduction** ($53,201.2\,ms$ saved relative to the 60s observation window; paired $SE = 247.0\,ms$).
- **Evidence Classification:** `SIMULATED` / `CALCULATED`

### Scenario 5: Repeated Alerts Flapping (`repeated_alerts`)
- **Alert Ingestion:** 5 alerts injected within a 20s window.
- **Policy Behavior:** Primary alert triggered incident diagnosis and container restart; remaining 4 alerts were suppressed by policy cooldown ($300s$ window).
- **Detection Latency:** Mean: $1,413.4 \pm 249.0\,ms$
- **Recovery Duration:** Mean: $2,301.0 \pm 246.5\,ms$
- **Total Outage Duration:** Mean: $4,564.4 \pm 433.9\,ms$ vs Control $60,000.0\,ms$ ($92.4\%$ reduction)
- **Outcome:** Zero duplicate recovery executions; zero alert storm cascading.
- **Evidence Classification:** `SIMULATED` / `CALCULATED`

### Scenario 6: Recovery Verification Failure Gate (`verification_failure`)
- **Fault Description:** Container restart simulated but post-recovery health probe failed (`/healthz` timeout).
- **Resolution State:** Incident was **NOT** marked resolved (`recovery_success = False`).
- **Escalation:** Incident state mutated to `escalated` ($100.0\%$ escalation rate) and routed to human on-call paging.
- **Outage Duration:** Right-censored at $60,000.0\,ms$ benchmark observation window.
- **Safety Compliance:** $100.0\%$.
- **Evidence Classification:** `SIMULATED`

### Scenario 7: Unauthorized Recovery Block (`unauthorized_recovery`)
- **Actor:** Role `viewer`.
- **Target Mutation:** Dispatch recovery without `operator` or `admin` privilege.
- **Response:** HTTP 403 Forbidden.
- **Safety Compliance:** $100.0\%$ (Zero command dispatch; security audit logged).
- **Evidence Classification:** `SIMULATED` (API RBAC software gate)

### Scenario 8: Unapproved Recovery Hold (`unapproved_recovery`)
- **Action Type:** High-risk primary restart requiring manual sign-off.
- **Outcome:** Action held in `pending_approval`; execution engine safely aborted execution without human approval token.
- **Safety Compliance:** $100.0\%$.
- **Evidence Classification:** `SIMULATED` (Approval policy gate)

---

## 4. Scientific Rigor, Censored Control & Statistical Qualifications

### 1. Investigation of the 60,000 ms Control MTTR
- **Nature of the Metric:** The $60,000.0\,ms$ control duration is a **configured benchmark observation window timeout / right-censoring bound**, not an observed natural system recovery.
- **Survival Data Reality:** When autonomous recovery is disabled, or when remediation fails verification, the service does not heal itself at $60.000$ seconds; the benchmark simply terminates data collection.
- **Zero Variance:** Because every control run reaches this cutoff, sample standard deviation $s_{\text{control}} = 0.0\,ms$.

### 2. Statistical Test Applicability
- **Violation of Parametric Assumptions:** Classical Student's t-test and Welch's t-test assume continuous, non-degenerate distributions. Comparing a variable sample ($s_E > 0$) against a degenerate constant ($s_C = 0.0\,ms$) violates these assumptions.
- **Removal of Unadjusted P-Values:** Prior informal notations of "$p < 0.01$" or "$p < 0.05$" have been audited and replaced with exact descriptive statistics and paired standard errors ($SE = s_E / \sqrt{N}$).
- **Paired Matched-Seed Analysis:** Because runs share identical pseudorandom seeds ($Seed_i = 42 + i$), the comparison is a paired difference against the observation window ceiling. The effect size ($\Delta T > 53,000\,ms$) exceeds the standard error by over $180\times$, establishing an indisputable descriptive reduction relative to the 60s benchmark cap.

### 3. Investigation of the 200 ms Dispatch Overhead
- **Exact Interval:** $t_{\text{rec\_start}} - t_{\text{detect}} = 200.0\,ms$.
- **Architectural Meaning:** This intentional fixed duration represents the platform's policy evaluation, allowlist verification, RBAC role validation, and asynchronous worker task queuing latency.
- **Additive Decomposition:** In every executed recovery run, total outage duration strictly satisfies:
  $$T_{\text{outage}} = T_{\text{detect}} + 200.0\,ms + T_{\text{recovery}} + T_{\text{verify}}$$
- **Reporting Clarity:** In previous summary tables, only $T_{\text{detect}}$ and $T_{\text{recovery}}$ were listed, creating an apparent 200 ms gap when summed with verification delays. The tables in Section 3 now explicitly display $T_{\text{dispatch}} = 200.0\,ms$, guaranteeing exact additive reconciliation across all 15 raw runs.

---

## 5. Scenario Independence Proof & Simulated Performance Hierarchy

### Simulated Scenario Performance Hierarchy — Seed 42, N=5

Scenarios 2, 3, and 4 simulate distinct failure modes with independent simulation paths, detection parameters, and simulated remediation actions. None of these actions perform live host or container mutations; all operations are strictly simulated within `RECOVERY_SIMULATION_MODE=true`:

1. **Scenario 2 (`service_unavailable`) — Simulated Failure Condition: Container crash / HTTP 503:**
   - Probes detect connection loss fast ($1,552.6 \pm 280.1\,ms$).
   - Simulated container restart (`restart_container`) models cold process boot lifecycle ($2,601.0 \pm 246.5\,ms$).
   - Verification readiness probe delay: $800.0\,ms$.
   - Yields mean simulated MTTR of **$5,153.6 \pm 461.4\,ms$** (Median: $4,979.7\,ms$).

2. **Scenario 3 (`high_error_rate`) — Simulated Failure Condition: Elevated 500 error rate (22%):**
   - Sliding-window rate accumulation requires sample collection across traffic window ($1,902.6 \pm 280.1\,ms$).
   - Simulated worker-pool recycling (`restart_pool`) models rapid in-place process reload ($1,834.2 \pm 205.4\,ms$).
   - Warm health verification delay: $600.0\,ms$.
   - Yields mean simulated MTTR of **$4,536.8 \pm 426.7\,ms$** (Median: $4,394.4\,ms$).

3. **Scenario 4 (`resource_exhaustion`) — Simulated Failure Condition: CPU & Memory Saturation (> 90%):**
   - Multi-scrape sustained utilization check requires consecutive confirmation cycles ($2,531.0 \pm 342.4\,ms$).
   - Simulated service scaling (`scale_service`) models horizontal pod replica scheduling & startup ($3,067.8 \pm 287.6\,ms$).
   - Capacity settling & traffic shedding delay: $1,000.0\,ms$.
   - Yields mean simulated MTTR of **$6,798.8 \pm 552.4\,ms$** (Median: $6,596.7\,ms$).

> [!NOTE]
> **Safety & Scope Boundary:** Simulated container restart, worker-pool recycling, and service scaling are executed entirely as software simulation states in the experiment harness. They are never described or represented as actual live infrastructure remediation.

---

## 6. Reproducibility Guarantee

Every benchmark figure reported above was generated using deterministic seed pinning ($Seed = 42 + run\_number$) and can be independently replicated by executing:

```bash
pytest backend/tests/test_phase14_experiments.py -v
```
