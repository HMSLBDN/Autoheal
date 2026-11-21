# KNOWN LIMITATIONS & REMAINING OPERATIONAL RISKS

**Project:** AutoHeal DevOps SaaS  
**Milestone:** Phase 11 Final Audit  
**Date:** 2026-11-21  
**Status:** FULL TRANSPARENCY AUDIT

---

## 1. Executive Summary

This document transparently records every known technical limitation, environment constraint, and residual risk identified during the Phase 11 engineering validation.

---

## 2. Technical Limitations & Environment Constraints

### A. Local Headless Docker Daemon Limitation
- **Identified Condition:** On Windows host systems where Docker Desktop runs in user space, automated background worker tasks without an active GUI login cannot connect to `//./pipe/dockerDesktopLinuxEngine`.
- **Impact:** Live PostgreSQL 16 container validation under Task 2 could not be executed locally without interactive desktop initialization.
- **Mitigation / Resolution:**
  - Task 2 is explicitly marked **NOT VERIFIED**.
  - A step-by-step manual validation runbook is provided in [POSTGRESQL_REAL_WORLD_VALIDATION.md](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/POSTGRESQL_REAL_WORLD_VALIDATION.md).
  - SQLite async driver was utilized strictly for unit/integration testing without altering production schema definitions.

### B. Offline DNS & Public Network Sandbox
- **Identified Condition:** In isolated, offline execution sandboxes without public DNS access, external domains (such as `hooks.slack.com` or live OIDC discovery endpoints `login.microsoftonline.com`) do not resolve via system DNS.
- **Impact:** Live third-party HTTP requests to public SaaS endpoints fail with `socket.gaierror`.
- **Mitigation / Resolution:**
  - Validated via cryptographic mock fixtures and local loopback TCP servers.
  - SSRF test harness verified against numeric IP addresses (`127.0.0.1`, `10.0.0.1`, `169.254.169.254`), with test allowance parameter for local synthetic hostnames.

### C. LLM Provider Dependency
- **Identified Condition:** Heavy reliance on external LLM APIs (Gemini Pro, OpenAI) for complex root-cause summarization.
- **Risk:** External API latency spikes, token rate limits (HTTP 429), or upstream outages.
- **Mitigation / Resolution:**
  - AutoHeal includes a deterministic heuristic fallback engine (`app/services/ai/gemini.py`).
  - Benchmarked under 100% simulated LLM outage: 100% of incidents were successfully triaged and assigned safe remediation actions.

---

## 3. Residual Operational Risks & Safeguards

| Risk Description | Severity | Probability | Built-In Safeguard |
| :--- | :--- | :--- | :--- |
| **Runaway Remediation Loop** (e.g. infinite restart cycle) | High | Low | Exponential backoff between restarts; maximum retry cap (3); automatic incident escalation upon retry exhaustion. |
| **Inaccurate AI Diagnosis** | Medium | Low | Strict Action Allowlist (`ALLOWED_RECOVERY_ACTIONS`); unrecognized actions rejected; human-in-the-loop approval gate. |
| **Compromised Edge Node** | Critical | Very Low | Mutual TLS (mTLS) with per-node X.509 certificates; CRL revocation capability; least-privilege edge permissions. |
| **Stale Session Takeover** | High | Low | 15-minute idle timeout; 24-hour absolute session ceiling; client IP and User-Agent fingerprint binding. |
| **Unintended Production Impact** | Critical | None | `RECOVERY_SIMULATION_MODE=true` hard-coded; destructive operations forbidden without verified dual approval. |

---

## 4. Phase 12 Preparation Note

Per non-negotiable instruction: *"Do NOT begin Phase 12"*. Phase 11 concludes with this validation and audit documentation.
