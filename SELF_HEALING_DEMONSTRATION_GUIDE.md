# SELF-HEALING DEMONSTRATION & FAILURE RECOVERY GUIDE

**Project:** AutoHeal DevOps SaaS  
**Harness Script:** `scripts/run_self_healing_demonstration.py`  
**Security Guardrail:** `RECOVERY_SIMULATION_MODE=true` (Hard-Locked)  
**Date:** 2026-11-21  
**Status:** ALL SCENARIOS VALIDATED & REPRODUCIBLE

---

## 1. Overview & Principles

AutoHeal's self-healing engine follows a strict closed-loop lifecycle:
$$\text{Telemetry} \longrightarrow \text{Detection} \longrightarrow \text{Triage} \longrightarrow \text{AI Recommendation} \longrightarrow \text{Operator Approval} \longrightarrow \text{Simulated Action} \longrightarrow \text{Verification} \longrightarrow \text{Resolution}$$

A fundamental invariant enforced in Phase 12:
> **An incident MUST NEVER be resolved unless post-remediation health verification explicitly PASSES.**  
> If verification fails, the incident remains open/investigating and is escalated to the on-call SRE team.

---

## 2. Scenario A: Successful Autonomous Self-Healing (Pod CrashLoop)

```
[A.1] Monitoring establishes baseline metrics for service 'checkout-api'...
      (CPU: 18%, p95 latency: 22.4ms, error rate: 0.00%)
[A.2] Controlled failure injected: JVM OutOfMemoryError / Pod CrashLoopBackOff (exit code 137).
[A.3] Prometheus Alert fired -> Alertmanager -> AutoHeal Incident Created: INC-70bb38.
[A.4] Automated Diagnostic Evidence Collected:
      - Log: "Container killed by Linux kernel OOMKiller (exit code 137)"
      - Metric: "Memory utilization reached 512MB limit (100%)"
[A.5] AI Diagnostic Engine analyzes incident:
      - Probable Root Cause: "memory_exhaustion"
      - Recommended Action: "restart_service" (allowlist verified, confidence: 0.96)
[A.6] Human Operator 'admin@autoheal.io' approves action REC-e70c69.
[A.7] Recovery Engine executes simulated action:
      [SIMULATED] kubectl rollout restart deployment/checkout-api -n production
[A.8] Post-remediation health check executes:
      HTTP GET http://localhost:8080/healthz -> 200 OK (Pod running, error rate 0.00%)
      Verification: PASSED
[A.9] Incident INC-70bb38 marked RESOLVED! Recovery status: Verified.
[A.10] Cryptographic Audit Log Entry sealed with SHA-256 hash: 5c06310ec2d31efb...
```

---

## 3. Scenario B: Failed Recovery & SRE Escalation (Storage Corruption)

```
[B.1] Persistent storage corruption detected on 'db-read-replica-02'.
      Incident created: INC-ddcba5 (Severity: critical, Status: open).
[B.2] AI Engine recommends 'restart_service'. Operator approves simulated execution.
[B.3] Recovery Engine executes restart. Post-remediation verification probe is dispatched:
      HTTP GET /healthz -> 503 SERVICE UNAVAILABLE (Read-only filesystem error).
      Verification: FAILED. Action marked FAILED.
[B.4] CRITICAL SAFETY INVARIANT TESTED:
      - Incident status remains 'investigating'.
      - Recovery status updated to 'Verification Failed - Escalated to On-Call SRE'.
      - Incident CANNOT be closed until underlying storage is repaired.
[B.5] Security Incident Failure & Escalation Audit Log sealed: 662124fafe20d64b...
```

---

## 4. How to Run the Demonstration

Execute the standalone script anytime:

```bash
.venv\Scripts\python.exe scripts/run_self_healing_demonstration.py
```

The script outputs color-coded log steps, calculates execution duration, and writes the complete JSON evidence payload to `monitoring/self_healing_demo_results.json`.
