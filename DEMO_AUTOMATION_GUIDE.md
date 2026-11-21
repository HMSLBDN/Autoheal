# AutoHeal DevOps — Phase 9 Demo Automation Guide

## 1. Overview

The Phase 9 Demo Automation Script (`scripts/run_phase9_demo.py`) provides an autonomous, verifiable end-to-end demonstration of the full operational lifecycle across 17 distinct steps.

---

## 2. Quickstart Execution

### Running in Python Environment:
```bash
# Using the workspace virtual environment:
.venv/Scripts/python.exe scripts/run_phase9_demo.py

# Or on Linux / macOS:
python3 scripts/run_phase9_demo.py
```

### Running via PowerShell:
```powershell
.\.venv\Scripts\python.exe scripts\run_phase9_demo.py
```

---

## 3. The 17-Step Verification Workflow

| Step | Operation | Verification Target |
|---|---|---|
| **01** | Stack Availability | FastAPI sub-routers loaded cleanly |
| **02** | Health Verification | `/api/v1/health` reports status `healthy` |
| **03** | Telemetry Scrape | Baseline availability (99.98%), error rate (0.08%), latency (145ms) |
| **04** | Inject Failure | Simulated error rate spike (2.45% > 1.0% SLA threshold) |
| **05** | Incident Creation | Incident record generated (`INC-...`, Critical severity) |
| **06** | AI Root Cause Diagnosis | Multi-signal analysis formulated with 88% confidence score |
| **07** | Risk Score & Anomalies | Multidimensional risk index (78/100, High Risk) computed |
| **08** | Recovery Preconditions | Recovery simulation mode active (`RECOVERY_SIMULATION_MODE=true`) |
| **09** | Notification Dispatch | Outbound alert dispatched to Slack and Signed Webhook |
| **10** | Delivery Verification | HMAC-SHA256 signature and idempotency key audited |
| **11** | Collaboration Note | Operator logs triage comment in communication thread |
| **12** | Acknowledgment | Alert acknowledged; escalation timeout clock silenced |
| **13** | Escalation Policy | Multi-level escalation policy evaluated with quiet hours |
| **14** | Deployment Correlation | Release `v2.5.0-rc1` correlated without false causation |
| **15** | Canary Rollout Evaluation | Baseline vs canary deltas evaluated (`rollback_recommended`) |
| **16** | Operations Timeline | Unified timeline aggregated across all operational categories |
| **17** | Executive Post-Mortem | Structured incident summary and JSON post-mortem compiled |

---

## 4. Expected Output
The script produces ANSI-colored status output terminating in:
```
================================================================================
  PHASE 9 END-TO-END DEMO AUTOMATION COMPLETED WITH 100% SUCCESS!
================================================================================
```
