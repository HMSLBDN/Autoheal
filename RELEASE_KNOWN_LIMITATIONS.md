# AutoHeal DevOps — Release Known Limitations & Boundaries

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1)  
**Applicability:** Evaluators, Researchers, Systems Engineers, Compliance Reviewers  
**Mandate:** Honest, unambiguous disclosure of system boundaries, simulation constraints, and statistical parameters.

---

## 1. Simulation-Only Recovery Boundary

### Constraint
All recovery actions executed by AutoHeal DevOps in this Release Candidate are strictly simulated via `SimulatedAgentClient` under `RECOVERY_SIMULATION_MODE=true`.

### Technical Boundaries
- The platform **does not** execute `docker restart`, `kubectl delete pod`, or systemd process modifications on the host machine.
- The platform **does not** mount `/var/run/docker.sock` and has no direct access to container runtimes.
- Actions such as `restart_container`, `restart_pool`, and `scale_service` simulate execution duration, verify cryptographic signatures, validate allowlists, and return simulated execution receipts with SHA-256 hashes.
- **Reporting Rule:** Simulated recovery must never be described as live container remediation or physical infrastructure repair in research papers or pilot documentation.

---

## 2. Right-Censored Control Horizon ($T_{\text{cutoff}} = 60,000.0\,\text{ms}$)

### Constraint
In the benchmarking and evaluation framework, control trials (recovery disabled) do not run indefinitely. They are terminated at an observation ceiling of $60,000.0\,\text{ms}$ (60 seconds).

### Statistical Implications
- The recorded control duration of $60,000.0\,\text{ms}$ with sample standard deviation $s = 0.0\,\text{ms}$ represents a right-censored observation horizon, not a true measured natural recovery time.
- MTTR reduction percentages (e.g., 91.6% reduction in Scenario 2) are calculated strictly relative to this 60-second observation window ($1 - \text{MTTR} / 60000$).
- If unmitigated failures persist indefinitely, the real-world reduction relative to infinite downtime is asymptotically 100%, but mathematically bounded in our benchmarks at the 60s observation window.

---

## 3. Sample Size & Statistical Parameters ($N=5$, Seed 42)

### Constraint
Published benchmark statistics in `BENCHMARK_RESULTS.md` are derived from $N=5$ runs per scenario with initial pseudo-random seed 42.

### Statistical Guidelines
- Because $N=5$ is a modest sample size, metric distributions display a small sample size flag (`small_sample_size: true`).
- Variance is expressed using the sample standard deviation ($s$, with $N-1$ degrees of freedom) and the **Standard Error of the Mean** ($SEM = s / \sqrt{N}$).
- No claims of universal asymptotic statistical significance or parametric p-values are made. The results represent deterministic, reproducible performance within the defined simulation model.

---

## 4. AI Diagnostics & Heuristic Fallback

### Constraint
The AI root-cause diagnosis engine relies on the Google Gemini API (via HTTP).

### Resilience Boundary
- If no Gemini API key is configured (`AI_API_KEY=""`), or if network partition occurs, or if API rate limits (HTTP 429) are reached, the system engages the **Deterministic Heuristic Engine**.
- The fallback engine provides standardized, rule-based root causes and allowlist recommendations based on status codes and threshold violations, but lacks the creative narrative synthesis of the full LLM.

---

## 5. Deployment & Clustering Scope

### Scope for v0.1.0-rc1
- The platform is packaged and validated for single-host Docker Compose environments.
- Multi-region clustering, multi-datacenter consensus, and active-active multi-primary database replication are outside the scope of this release candidate.
- High Availability (HA) configurations should rely on external cloud managed services (AWS RDS, ElastiCache) when graduating beyond the local pilot stage.

---

## 6. Mandatory Human-in-the-Loop Recovery

### Safety Policy
- AutoHeal DevOps v0.1.0-rc1 is deliberately configured to require explicit operator authorization for all recovery actions.
- Fully autonomous, unattended self-healing execution is blocked by policy to ensure safety during pilot evaluation.
