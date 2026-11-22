# AUTOHEAL DEVOPS — EXPERIMENT METHODOLOGY & EVALUATION FRAMEWORK
## Phase 14: Reproducible Evaluation, Experiment Automation & Performance Benchmarking

---

## 1. Executive Summary & Objective

The objective of the AutoHeal DevOps Evaluation Framework is to establish an empirical, reproducible, and verifiable methodology for benchmarking autonomous self-healing, anomaly detection, recovery policy evaluation, and post-remediation health verification.

All experiments are conducted under strict safety guarantees:
- **`RECOVERY_SIMULATION_MODE=true`**: All container, host, and orchestrator lifecycle mutations are executed exclusively via sandboxed simulation adapters.
- **Zero Raw Shell or Socket Exposure**: The Docker daemon socket (`/var/run/docker.sock`) is never exposed, mounted, or accessed by FastAPI or worker processes.
- **Deterministic Seed Isolation**: Every multi-run trial uses deterministic pseudorandom seed derivation ($Seed_i = Seed_{base} + i$) ensuring bit-for-bit repeatability across independent runs and environments.

---

## 2. Evidence Classification Framework

To uphold scientific integrity and research credibility, all telemetry, measurements, and reported figures are explicitly classified into one of four mutually exclusive evidence tiers:

| Classification | Definition | Application in AutoHeal |
| :--- | :--- | :--- |
| **`MEASURED`** | Directly observed wall-clock timings and system responses collected by probes. | Detection latency, API response times, request throughput, database query durations. |
| **`CALCULATED`** | Mathematically derived aggregations, standard errors, percentages, and statistical distributions. | Mean, median, std dev, p95, MTTR improvement %, outage duration reduction. |
| **`SIMULATED`** | Controlled model responses simulating infrastructure behavior under fixed parameters. | Simulated container restarts, service scale adjustments, network delay injection. |
| **`SYNTHETIC`** | Artificially generated demo traffic or mock datasets for illustrative UI presentation. | Demo workspace mock cards, onboarding step checklists. |

> [!IMPORTANT]
> Simulated container remediation is never represented as physical hardware or live container manipulation. All benchmark reports clearly state the simulation tier.

---

## 3. The 8 Deterministic Benchmark Scenarios

The framework implements 8 standardized evaluation scenarios designed to test distinct aspects of the self-healing and safety pipeline:

### Scenario 1: Healthy Baseline (`healthy_baseline`)
- **Objective:** Establish the false-alarm baseline and verify that normal system variance does not trip false recovery actions.
- **Fault Injected:** None. Traffic parameters: CPU 22–38%, memory 40–55%, error rate 0.0–0.4%, p95 40–75ms.
- **Success Criteria:** False-positive rate = 0.0%, recovery attempts = 0, total outage duration = 0.0ms.

### Scenario 2: Service Unavailable Outage (`service_unavailable`)
- **Objective:** Evaluate autonomous recovery under complete HTTP 503 outage compared to unmitigated manual escalation.
- **Fault Injected:** HTTP 503 Service Unavailable, 100% error rate, connection failure.
- **Recovery Operation:** `restart_container` (cold container reboot lifecycle).
- **Evaluation Modes:**
  - *Recovery Enabled:* Policy triggers simulated container restart; post-recovery readiness probe verifies health; outage resolved in ~4,700–5,900ms.
  - *Recovery Disabled (Control):* Outage remains unmitigated until benchmark timeout window (60,000ms standard; right-censored).
- **Success Criteria:** MTTR reduction > 85%, verified health check passed.

### Scenario 3: High Error Rate Surge (`high_error_rate`)
- **Objective:** Evaluate threshold detection and policy cooldown under elevated 5xx error rates (18–26%).
- **Fault Injected:** 500 Internal Server Error rate jumping to 22% (threshold 5.0%).
- **Recovery Operation:** `restart_pool` (in-place worker pool recycling & process reload).
- **Evaluation Modes:**
  - *Recovery Enabled:* Sliding-window rate accumulator triggers worker pool recycling; outage resolved in ~4,100–5,300ms.
  - *Recovery Disabled (Control):* Outage remains unmitigated and right-censored at 60,000ms.
- **Success Criteria:** Detection within ~1,900ms, error rate restored to < 0.5%, MTTR reduction > 90%.

### Scenario 4: Resource Exhaustion (`resource_exhaustion`)
- **Objective:** Evaluate saturation response under CPU and memory pressure exceeding 95%.
- **Fault Injected:** CPU 92–98.5%, memory 88–96%, latency degradation.
- **Recovery Operation:** `scale_service` (horizontal pod replica provisioning & scaling).
- **Evaluation Modes:**
  - *Recovery Enabled:* Multi-scrape saturation check triggers replica scale-out; stabilization verified; outage resolved in ~6,300–7,700ms.
  - *Recovery Disabled (Control):* Outage remains unmitigated and right-censored at 60,000ms.
- **Success Criteria:** Policy identifies capacity bottleneck, triggers horizontal scale-out, CPU restored to < 45%.

### Scenario 5: Repeated Alerts Flapping (`repeated_alerts`)
- **Objective:** Validate policy cooldown windows and deduplication mechanisms to prevent cascading remediation loops.
- **Fault Injected:** 5 rapid alert bursts within a 20-second window.
- **Success Criteria:** Primary alert triggers recovery evaluation; 4 subsequent flapping alerts are suppressed by cooldown policy; zero duplicate restarts.

### Scenario 6: Recovery Verification Failure Gate (`verification_failure`)
- **Objective:** Verify incident resolution integrity when remediation fails post-recovery health probes.
- **Fault Injected:** Remediation command executes, but readiness probes continue to fail (HTTP 502).
- **Success Criteria:** Incident is **NOT** marked resolved; state machine escalates incident to on-call human operator; `safety_compliant=True`.

### Scenario 7: Unauthorized Recovery Block (`unauthorized_recovery`)
- **Objective:** Evaluate RBAC access control by simulating recovery requests by unauthorized roles (e.g. `viewer`).
- **Fault Injected:** Mutation request dispatched by non-operator identity.
- **Success Criteria:** Request rejected with HTTP 403 Forbidden; zero command dispatch; security audit logged.

### Scenario 8: Unapproved Recovery Hold (`unapproved_recovery`)
- **Objective:** Validate sign-off gating for destructive or high-risk recovery actions requiring human approval.
- **Fault Injected:** High-risk remediation dispatched without cryptographic sign-off.
- **Success Criteria:** Action halted in `pending_approval`; execution blocked; incident escalated for human review.

---

## 4. Multi-Run Repeatability & Seed Pinning

To guarantee scientific reproducibility:
1. Each experiment defines a base seed (e.g., $Seed_{base} = 42$).
2. Run $i \in [1, N]$ instantiates an independent `random.Random(Seed_{base} + i)`.
3. Metric jitter, detection timing, and telemetry values are mathematically derived from this PRNG sequence.
4. Rerunning the experiment with the same configuration produces identical metrics and sequence events.

---

## 5. Statistical Rigor, Censored Controls & Sample Size Awareness

Small sample sizes ($N < 5$) produce unstable variances and false confidence intervals. The AutoHeal Analytics Engine enforces:
- **Small Sample Warning:** If $N < 5$, the metric distribution explicitly flags `small_sample_size: true` and attaches a warning:
  > *"Sample size (N=X) is below minimum statistical confidence threshold (N=5). Results indicate preliminary trends; variance and significance estimates may be unstable."*
- **Censored Control Handling:** In control trials (recovery disabled) and verification failures, outages do not resolve naturally within the benchmark timeframe and are bounded by the 60,000 ms observation window ($s = 0.0\,ms$). Because control data is right-censored with zero variance, classical parametric t-tests are invalid; results are reported descriptively with paired standard errors ($Diff > 2 \times SE$).
- **Statistical Significance Classification:** Pairwise comparison (Enabled vs. Disabled) requires $N \ge 5$ in both groups before reporting statistically significant MTTR reduction against the observation window ceiling. Parametric p-values are not claimed without full survival models.
