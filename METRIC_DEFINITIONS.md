# AUTOHEAL DEVOPS — METRIC DEFINITIONS & FORMULAS
## Phase 14: Reproducible Performance & Self-Healing Benchmarking

---

## 1. Metric Overview & Units

All temporal and statistical metrics in AutoHeal DevOps are measured in milliseconds ($ms$) or seconds ($s$) and computed using unbiased sample estimators.

```
       Fault Injected          Incident Detected       Recovery Started        Recovery Completed       Health Restored
            │                         │                       │                       │                       │
Timeline ───┼─────────────────────────┼───────────────────────┼───────────────────────┼───────────────────────┼───►
            │                         │                       │                       │                       │
            ◄─── Detection Latency ───►                       ◄── Recovery Duration ──►                       │
            │                                                                                                 │
            ◄──────────────────────────── Total Outage Duration (MTTR) ───────────────────────────────────────►
```

---

## 2. Core Scalar Metrics

### 1. Detection Latency ($T_{\text{detect}}$)
- **Definition:** Elapsed duration from the moment a fault is injected or an infrastructure degradation begins until the platform generates a formal incident record.
- **Formula:**
  $$T_{\text{detect}} = (Timestamp_{\text{detected}} - Timestamp_{\text{fault\_injected}}) \times 1000 \quad [ms]$$
- **Evidence Classification:** `SIMULATED` / `CALCULATED` (from simulation timestamps)
- **Applicable Scenarios:** Scenarios 2 through 8. (Scenario 1 Healthy Baseline records $0.0\,ms$ unless a false alarm occurs).

### 2. Recovery Duration ($T_{\text{recovery}}$)
- **Definition:** Elapsed duration for the remediation adapter to execute the allowlisted action (e.g. simulated container restart, worker pool reload, or service scale-out).
- **Formula:**
  $$T_{\text{recovery}} = (Timestamp_{\text{recovery\_completed}} - Timestamp_{\text{recovery\_started}}) \times 1000 \quad [ms]$$
- **Evidence Classification:** `SIMULATED`
- **Applicable Scenarios:** Executed recovery actions only. In Control (Recovery Disabled) modes or blocked actions, $T_{\text{recovery}} = \text{null}$ (honestly treated as N/A).

### 3. Total Outage Duration / MTTR ($T_{\text{outage}}$)
- **Definition:** Total elapsed wall-clock duration during which the target service remained unavailable or in degraded performance before health verification passed.
- **Formula:**
  $$T_{\text{outage}} = (Timestamp_{\text{health\_restored}} - Timestamp_{\text{fault\_injected}}) \times 1000 \quad [ms]$$
- **Evidence Classification:** `CALCULATED` (from simulated timestamps)
- **Control Timeout & Right-Censoring:** In control runs where autonomous recovery is disabled or verification fails, unmitigated outages default to the standard benchmark observation timeout window ($T_{\text{cutoff}} = 60,000\,ms$, $s = 0.0\,ms$). This represents a right-censored observation ceiling ($MTTR > 60\,s$), not an observed natural resolution.

---

## 3. Aggregate Rate Metrics

### 1. Recovery Success Rate ($R_{\text{success}}$)
- **Definition:** Percentage of attempted recovery actions that resulted in a verified healthy post-remediation probe.
- **Formula:**
  $$R_{\text{success}} = \left( \frac{\sum \text{Runs with } \text{recovery\_success} = \text{true}}{\sum \text{Runs with } \text{recovery\_attempted} = \text{true}} \right) \times 100\%$$
- **Unit:** Percentage ($0.0\% - 100.0\%$)

### 2. False-Positive Rate ($R_{\text{FP}}$)
- **Definition:** Percentage of healthy baseline runs where metric noise falsely triggered an incident or remediation action.
- **Formula:**
  $$R_{\text{FP}} = \left( \frac{\sum \text{Runs with } \text{is\_false\_positive} = \text{true}}{N_{\text{total\_runs}}} \right) \times 100\%$$
- **Target:** $0.0\%$ under standard baseline conditions.

### 3. Safety Compliance Rate ($R_{\text{safety}}$)
- **Definition:** Percentage of trials adhering strictly to the security policy (zero arbitrary shell execution, zero Docker socket exposure, rejected unauthorized roles, and blocked unapproved actions).
- **Formula:**
  $$R_{\text{safety}} = \left( \frac{\sum \text{Runs with } \text{safety\_compliant} = \text{true}}{N_{\text{total\_runs}}} \right) \times 100\%$$
- **Target:** $100.0\%$ non-negotiable.

### 4. Escalation Rate ($R_{\text{escalate}}$)
- **Definition:** Percentage of incidents routed to human on-call operators due to verification failure, missing approval, or policy constraints.
- **Formula:**
  $$R_{\text{escalate}} = \left( \frac{\sum \text{Runs with } \text{escalated} = \text{true}}{N_{\text{total\_runs}}} \right) \times 100\%$$

---

## 4. Statistical Distribution Formulas

For any scalar metric sample $X = \{x_1, x_2, \dots, x_N\}$:

- **Sample Mean ($\bar{x}$):**
  $$\bar{x} = \frac{1}{N} \sum_{i=1}^{N} x_i$$
- **Sample Median ($\tilde{x}$):**
  $$\tilde{x} = \begin{cases} x_{(\frac{N+1}{2})} & \text{if } N \text{ is odd} \\ \frac{x_{(\frac{N}{2})} + x_{(\frac{N}{2} + 1)}}{2} & \text{if } N \text{ is even} \end{cases}$$
- **Sample Standard Deviation ($s$):**
  $$s = \sqrt{\frac{1}{N-1} \sum_{i=1}^{N} (x_i - \bar{x})^2} \quad (\text{for } N \ge 2)$$
- **95th Percentile ($P_{95}$):**
  Nearest rank index $k = \lceil 0.95 \times N \rceil$ from ordered sample $X_{(1)} \le X_{(2)} \le \dots \le X_{(N)}$.

---

## 5. Comparative Improvement Formulas & Censoring Handling

When comparing Recovery Enabled ($E$) against Recovery Disabled / Control ($D$):

- **Absolute Outage Reduction ($\Delta T$):**
  $$\Delta T = \bar{T}_{\text{outage}, D} - \bar{T}_{\text{outage}, E} \quad [ms]$$
- **Relative MTTR Improvement Percentage ($I_{\text{MTTR}}$):**
  $$I_{\text{MTTR}} = \left( \frac{\bar{T}_{\text{outage}, D} - \bar{T}_{\text{outage}, E}}{\bar{T}_{\text{outage}, D}} \right) \times 100\%$$
- **Standard Error of Difference ($SE_{\text{diff}}$):**
  In matched-seed paired trials where the control group is bounded by the fixed observation timeout ($s_D = 0.0$):
  $$SE_{\text{diff}} = \frac{s_E}{\sqrt{N_E}}$$
- **Descriptive Benchmark Threshold:** An improvement relative to the observation ceiling is declared descriptively significant if $N_E \ge 5$, $N_D \ge 5$, and $\Delta T > 2 \times SE_{\text{diff}}$. Because the control group is right-censored at $60,000\,ms$, parametric p-values from unconstrained survival models are not claimed.
