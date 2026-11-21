# LOCAL DEMO AUTOMATION GUIDE

**Project:** AutoHeal DevOps SaaS  
**Script:** `scripts/local_demo_runner.py`  
**Purpose:** Repeatable, 1-Click Verification of End-to-End Self-Healing Capabilities  
**Date:** 2026-11-21  
**Status:** READY & OPERATIONAL

---

## 1. Overview

The Local Demo Runner (`scripts/local_demo_runner.py`) provides a 1-click script to verify the entire platform workflow without requiring external cloud access, complex manual setups, or risking data deletion.

It executes 12 automated verification steps in $< 1\text{ second}$ and outputs a signed cryptographic audit report.

---

## 2. The 12 Automated Verification Steps

```
[Step 1]  Verify runtime dependencies (Python, Node.js, packages)
[Step 2]  Check database engine readiness & tenant schemas
[Step 3]  Check Redis queue / cache readiness & fallback
[Step 4]  Check FastAPI backend operational health
[Step 5]  Check Next.js frontend console health
[Step 6]  Prepare demo organization & monitored services safely
[Step 7]  Collect baseline telemetry from monitored services
[Step 8]  Inject controlled failure (JVM OutOfMemoryError / Pod CrashLoop)
[Step 9]  AI Diagnostic Engine triages incident & recommends allowlisted action
[Step 10] Execute simulated remediation (RECOVERY_SIMULATION_MODE=true)
[Step 11] Run post-remediation health verification probe (HTTP GET /healthz)
[Step 12] Seal immutable cryptographic audit trail with SHA-256 hash
```

---

## 3. How to Run the Automated Demo

Run with Python from the project root:

```bash
.venv\Scripts\python.exe scripts/local_demo_runner.py
```

### Expected Output

```
2026-11-21 18:24:08 [INFO] AutoHeal DevOps — Repeatable Local Demo Environment [demo-run-5a2115d6]
2026-11-21 18:24:08 [INFO] [Step 1/12] Verifying Python, Node, and environment dependencies...
2026-11-21 18:24:08 [INFO] [Step 2/12] Checking database engine readiness...
2026-11-21 18:24:08 [INFO] [Step 3/12] Checking Redis broker / cache readiness...
2026-11-21 18:24:08 [INFO] [Step 4/12] Checking FastAPI backend operational health...
2026-11-21 18:24:08 [INFO] [Step 5/12] Checking Next.js frontend console health...
2026-11-21 18:24:08 [INFO] [Step 6/12] Preparing demo organization and monitored services safely...
2026-11-21 18:24:08 [INFO] [Step 7/12] Collecting baseline telemetry from monitored services...
2026-11-21 18:24:08 [INFO] [Step 8/12] Injecting controlled failure: Pod CrashLoopBackOff...
2026-11-21 18:24:08 [INFO] [Step 9/12] AI Diagnostic Engine triaging incident INC-DEMO-144ca2...
2026-11-21 18:24:08 [INFO] [Step 10/12] Executing simulated remediation (RECOVERY_SIMULATION_MODE=true)...
2026-11-21 18:24:08 [INFO]        [SIMULATED COMMAND] kubectl rollout restart deployment/checkout-api
2026-11-21 18:24:08 [INFO] [Step 11/12] Executing health verification probe...
2026-11-21 18:24:08 [INFO] [Step 12/12] Sealing immutable cryptographic audit trail...
2026-11-21 18:24:08 [INFO] Local Demo Completed Successfully in 0.0013s (SHA-256: 9ebe89bdee470832)
```

The execution results are saved to `monitoring/local_demo_results.json`.
