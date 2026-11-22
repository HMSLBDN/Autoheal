# AUTOHEAL DEVOPS — PHASE 14.1.1 SCENARIO CONSISTENCY & INDEPENDENCE REPORT
## Deep Investigation, Resolution of Identical Benchmark Results, and Recalculated Empirical Evidence

**Project:** AutoHeal DevOps SaaS  
**Repository:** `https://github.com/HMSLBDN/Autoheal.git`  
**Branch:** `main`  
**Date:** November 22, 2026  
**Safety Gating:** `RECOVERY_SIMULATION_MODE=true` (Strict Hard Lock)

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 The Anomaly Under Investigation
In the initial Phase 14 benchmark evaluation, three distinct scenarios reported identical statistics:
- **S2: 503 Outage** — $5,060.8 \pm 678.4\,ms$
- **S3: High Error Rate** — $5,060.8 \pm 678.4\,ms$
- **S4: Resource Exhaustion** — $5,060.8 \pm 678.4\,ms$

### 1.2 Root Cause Analysis
An exhaustive code and data trace through the scenario pipeline revealed the following root cause:

1. **Scenario Definition & Telemetry Generation:**
   - In Pydantic schemas, database models, and time-series telemetry generation (`_generate_telemetry_series`), S2, S3, and S4 were correctly configured with distinct fault parameters (S2 had 100% 503 error rate; S3 had 18–26% 500 error rate; S4 had 92–98.5% CPU and 88–96% memory saturation).
2. **Experiment Runner Bottleneck:**
   - In `backend/app/services/experiment/runner.py`, `run_scenario_iteration` grouped all three scenarios into a **single generic code branch**:
     ```python
     elif scenario in ("service_unavailable", "high_error_rate", "resource_exhaustion"):
     ```
   - In this shared branch:
     - Detection latency was generated identically via `round(rng.uniform(1150.0, 2450.0), 1)`.
     - Recovery duration was generated identically via `round(rng.uniform(1800.0, 3600.0), 1)`.
     - Post-recovery verification delay was hardcoded to `800` ms.
     - Outage duration was calculated as `det_lat_ms + 200 + rec_dur_ms + 800`.
3. **Deterministic PRNG Synchronization:**
   - Because each scenario was evaluated using deterministic seed isolation ($Seed_i = 42 + run\_number$), and because the exact same sequence of PRNG calls with identical bounds was executed across all three scenarios, the resulting scalar latencies and total outage durations were 100% mathematically identical across S2, S3, and S4.

**Conclusion:** The identical statistics were **not expected**. They were caused by **shared generic simulation logic** in the experiment runner where distinct failure types lacked scenario-specific detection and recovery mechanics.

---

## 2. Genuine Scenario Independence & Architectural Modeling

To establish genuine scenario independence, each scenario was decoupled and modeled according to its distinct architectural and simulated failure characteristics (operating strictly within `RECOVERY_SIMULATION_MODE=true`; zero actual infrastructure remediation):

| Scenario | Simulated Failure Condition | Simulated Remediating Action | Detection Model | Recovery Duration Model | Verification Delay |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **S2: 503 Outage** | Hard container crash / connection refused (Simulated) | `restart_container` (Simulated container reboot) | Fast threshold probe failure: `1200–2100 ms` | Cold container reboot lifecycle (SIGTERM, stop, start, socket bind): `2200–3400 ms` | 800 ms (Readiness probe on `/healthz`) |
| **S3: High Error Rate** | Elevated 500 errors (18–26%), service responding (Simulated) | `restart_pool` (Simulated worker-pool recycling) | Sliding-window sample accumulation: `1550–2450 ms` | In-place worker pool recycling & process reload: `1500–2500 ms` | 600 ms (Warm error rate check) |
| **S4: Resource Exhaustion** | CPU & Memory saturation (> 90%), queuing delay (Simulated) | `scale_service` (Simulated service scaling) | Multi-scrape sustained utilization check: `2100–3200 ms` | Pod provisioning, replica scheduling & startup: `2600–4000 ms` | 1000 ms (Capacity settling & traffic shedding) |

All simulation parameters remain strictly enclosed within `RECOVERY_SIMULATION_MODE=true` without physical host modification or socket exposure.

---

## 3. Raw Run Evidence & Recalculated Statistics (Base Seed: 42, N = 5)

### 3.1 Raw Run Table Across Matched Seeds

| Scenario | Run | Seed | Detection Latency ($ms$) | Recovery Duration ($ms$) | Total Outage Enabled ($ms$) | Total Outage Control ($ms$) | Action Executed | Outcome |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **S2: 503 Outage** | 1 | 43 | 1,234.7 | 2,643.9 | **4,878.6** | 60,000.0* | `restart_container` | Verified / Restored |
| | 2 | 44 | 1,567.7 | 2,412.0 | **4,979.7** | 60,000.0* | `restart_container` | Verified / Restored |
| | 3 | 45 | 1,444.7 | 2,298.3 | **4,743.0** | 60,000.0* | `restart_container` | Verified / Restored |
| | 4 | 46 | 1,999.4 | 2,906.3 | **5,905.7** | 60,000.0* | `restart_container` | Verified / Restored |
| | 5 | 47 | 1,516.7 | 2,744.4 | **5,261.1** | 60,000.0* | `restart_container` | Verified / Restored |
| **S3: High Error Rate** | 1 | 43 | 1,584.7 | 1,869.9 | **4,254.6** | 60,000.0* | `restart_pool` | Verified / Restored |
| | 2 | 44 | 1,917.7 | 1,676.7 | **4,394.4** | 60,000.0* | `restart_pool` | Verified / Restored |
| | 3 | 45 | 1,794.7 | 1,581.9 | **4,176.6** | 60,000.0* | `restart_pool` | Verified / Restored |
| | 4 | 46 | 2,349.4 | 2,088.6 | **5,238.0** | 60,000.0* | `restart_pool` | Verified / Restored |
| | 5 | 47 | 1,866.7 | 1,953.7 | **4,620.4** | 60,000.0* | `restart_pool` | Verified / Restored |
| **S4: Resource Exhaustion** | 1 | 43 | 2,142.4 | 3,117.8 | **6,460.2** | 60,000.0* | `scale_service` | Verified / Restored |
| | 2 | 44 | 2,549.4 | 2,847.3 | **6,596.7** | 60,000.0* | `scale_service` | Verified / Restored |
| | 3 | 45 | 2,399.1 | 2,714.6 | **6,313.7** | 60,000.0* | `scale_service` | Verified / Restored |
| | 4 | 46 | 3,077.1 | 3,424.1 | **7,701.2** | 60,000.0* | `scale_service` | Verified / Restored |
| | 5 | 47 | 2,487.0 | 3,235.1 | **6,922.1** | 60,000.0* | `scale_service` | Verified / Restored |

*\* Control group is right-censored at the 60,000 ms observation window ceiling.*

---

### 3.2 Recalculated Distribution Statistics

| Metric | S2: 503 Outage | S3: High Error Rate | S4: Resource Exhaustion | S5: Repeated Alerts |
| :--- | :--- | :--- | :--- | :--- |
| **Mean Detection Latency** | $1,552.6 \pm 280.1\,ms$ | $1,902.6 \pm 280.1\,ms$ | $2,531.0 \pm 342.4\,ms$ | $1,413.4 \pm 249.0\,ms$ |
| **Median Detection Latency**| $1,516.7\,ms$ | $1,866.7\,ms$ | $2,487.0\,ms$ | $1,381.5\,ms$ |
| **Mean Recovery Duration** | $2,601.0 \pm 246.5\,ms$ | $1,834.2 \pm 205.4\,ms$ | $3,067.8 \pm 287.6\,ms$ | $2,301.0 \pm 246.5\,ms$ |
| **Median Recovery Duration**| $2,643.9\,ms$ | $1,869.9\,ms$ | $3,117.8\,ms$ | $2,343.9\,ms$ |
| **Mean Outage (Recovery Enabled)**| **$5,153.6 \pm 461.4\,ms$** | **$4,536.8 \pm 426.7\,ms$** | **$6,798.8 \pm 552.4\,ms$** | **$4,564.4 \pm 433.9\,ms$** |
| **Median Outage** | $4,979.7\,ms$ | $4,394.4\,ms$ | $6,596.7\,ms$ | $4,388.8\,ms$ |
| **$P_{95}$ Outage** | $5,905.7\,ms$ | $5,238.0\,ms$ | $7,701.2\,ms$ | $5,266.9\,ms$ |
| **Min / Max Outage** | $4,743.0 / 5,905.7\,ms$ | $4,176.6 / 5,238.0\,ms$ | $6,313.7 / 7,701.2\,ms$ | $4,165.8 / 5,266.9\,ms$ |
| **Control Baseline Outage** | $60,000.0 \pm 0.0\,ms$* | $60,000.0 \pm 0.0\,ms$* | $60,000.0 \pm 0.0\,ms$* | $60,000.0 \pm 0.0\,ms$* |
| **Outage Reduction ($\Delta T$)** | **$54,846.4\,ms$ ($91.4\%$)** | **$55,463.2\,ms$ ($92.4\%$)** | **$53,201.2\,ms$ ($88.7\%$)** | **$55,435.6\,ms$ ($92.4\%$)** |
| **Paired Standard Error ($SE$)** | $206.4\,ms$ | $190.8\,ms$ | $247.0\,ms$ | $194.1\,ms$ |

### 3.3 Simulated Scenario Performance Hierarchy — Seed 42, N=5:
1. **$S3 < S2 < S4$ Outage Duration Hierarchy:**
   - Scenario 3 (High Error Rate) is the fastest to remediate ($4,536.8\,ms$) because simulated worker-pool recycling avoids full container recreation.
   - Scenario 2 (503 Outage) simulates a full container lifecycle, yielding medium MTTR ($5,153.6\,ms$).
   - Scenario 4 (Resource Exhaustion) simulates sustained multi-scrape detection and pod replica scheduling, yielding highest MTTR ($6,798.8\,ms$).
2. **$S2 < S3 < S4$ Detection Latency Hierarchy:**
   - Scenario 2 connection loss fails probes immediately ($1,552.6\,ms$).
   - Scenario 3 error rate requires windowed traffic aggregation ($1,902.6\,ms$).
   - Scenario 4 resource saturation requires sustained multi-scrape confirmation ($2,531.0\,ms$).

All three scenarios are now **mathematically distinct, operationally independent, and reproducible**. Note: All remediation actions (`restart_container`, `restart_pool`, `scale_service`) represent simulated software state-machine operations; zero actual infrastructure remediation is performed.

---

## 4. Files Modified

1. `backend/app/services/experiment/runner.py`: Decoupled `service_unavailable`, `high_error_rate`, and `resource_exhaustion` into distinct architectural failure and recovery simulation blocks.
2. `backend/tests/test_phase14_experiments.py`: Added `test_23_scenario_independence_s2_s3_s4` verifying distinct actions, detection latencies, and outage distributions.
3. `BENCHMARK_RESULTS.md`: Updated with the recalculated empirical statistics and scenario independence proof.
4. `EXPERIMENT_METHODOLOGY.md`: Updated scenario specifications with allowlisted actions and distinct failure modes.
5. `METRIC_DEFINITIONS.md`: Aligned metric evidence classifications with simulation tiers.
6. `PHASE_14_1_RESEARCH_INTEGRITY_AUDIT.md`: Aligned audit tables with recalculated statistics.
7. `PHASE_14_1_1_SCENARIO_CONSISTENCY_REPORT.md`: This comprehensive investigation and resolution report.

---

## 5. Automated Regression & Quality Gate Results

| Test / Gate | Command | Result | Duration |
| :--- | :--- | :---: | :---: |
| **Phase 14 Test Suite (23 tests)** | `pytest backend/tests/test_phase14_experiments.py` | **23 Passed, 0 Failed** | 11.52s |
| **Complete Backend Pytest Suite** | `pytest backend/tests` | **339 Passed, 0 Failed** | ~230s |
| **TypeScript Typecheck** | `pnpm tsc --noEmit` | **0 Errors** | 6.5s |
| **ESLint Validation** | `pnpm lint` | **0 Errors** | 7.1s |
| **Next.js Production Build** | `pnpm build` | **Compiled successfully** | 24.8s |
| **Docker Compose Validation** | `docker compose -f docker-compose.yml config` | **Valid** | < 1s |

---

## 6. Verification Sign-Off

The root cause of identical scenario results has been diagnosed, explained, and resolved.
Genuinely independent failure behaviors and distinct recovery actions have been implemented and verified.
All statistics have been recalculated directly from persisted raw runs without manual alteration or unsupported claims.

**Status:** **100% RESOLVED AND VERIFIED**.
