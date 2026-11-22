# AutoHeal DevOps — Release Candidate Report (v0.1.0-rc1)

**Document Version:** 1.0.0  
**Phase:** Phase 15 — Release Candidate, End-to-End Validation & Pilot Packaging  
**Release Tag:** `v0.1.0-rc1`  
**Repository:** [https://github.com/HMSLBDN/Autoheal.git](https://github.com/HMSLBDN/Autoheal.git)  
**Branch:** `main`  
**Baseline Commit:** `dfe7d55ad18d3461ff7b0dd9dfa1d4f443741ff6`  
**Operational Mode:** `RECOVERY_SIMULATION_MODE=true` (Mandatory Safety Hard Lock)

---

## 1. Executive Summary

This report establishes **AutoHeal DevOps v0.1.0-rc1** as a validated, reproducible, and packaged Release Candidate. AutoHeal DevOps is an AI-assisted incident detection, root-cause diagnosis, recovery orchestration, and post-remediation health verification platform built for Site Reliability Engineering (SRE) and DevOps teams.

The objective of Phase 15 is not feature expansion or UI redesign, but rigorous end-to-end operational validation, full test suite verification, security posture audit, and comprehensive packaging for pilot evaluators.

### Core Release Attributes
- **Zero Real Infrastructure Disruption:** Enforced by `RECOVERY_SIMULATION_MODE=true`. Recovery actions operate against cryptographic simulation adapters without Docker socket exposure or host shell access.
- **Auditable AI Diagnosis:** Combines LLM-driven anomaly explanation (Google Gemini 1.5/2.0) with a deterministic heuristic fallback engine to guarantee uninterrupted triage during network partition or quota exhaustion.
- **Closed-Loop Verification:** Remediations require explicit post-action telemetry probing against SLO thresholds; incidents are only resolved when service metrics satisfy recovery bounds.
- **Repeatable Benchmarking:** Integrated Monte Carlo experiment engine with seed-deterministic pseudo-random execution, right-censored control groups ($T_{\text{cutoff}} = 60,000.0\,\text{ms}$), and rigorous Standard Error of the Mean ($SEM = s / \sqrt{N}$) reporting.

---

## 2. Platform Architecture

The AutoHeal DevOps architecture comprises five decoupled layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Next.js 16 Presentation Layer                  │
│            (React 19, Tailwind CSS, Dark Navy Theme, SSE Updates)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST / SSE
┌───────────────────────────────────▼────────────────────────────────────┐
│                        FastAPI Application Core                        │
│  ┌───────────────────────┬──────────────────────┬────────────────────┐ │
│  │ Authentication & RBAC │ Incident Manager     │ Recovery Engine    │ │
│  │ (Argon2id, JWT)       │ (FSM, Evidence Log)  │ (Policy, Approval) │ │
│  ├───────────────────────┼──────────────────────┼────────────────────┤ │
│  │ Experiment Runner     │ AI Diagnosis & Rule  │ Telemetry Ingest   │ │
│  │ (Monte Carlo, S1-S5)  │ Fallback Subsystem   │ (Prometheus/Alerts)│ │
│  └───────────────────────┴──────────────────────┴────────────────────┘ │
└──────────────────┬───────────────────────────────┬─────────────────────┘
                   │                               │
┌──────────────────▼──────────────┐ ┌──────────────▼─────────────────────┐
│   PostgreSQL 16 Storage Layer   │ │    Redis 7.2 & Celery 5.4 Broker   │
│  (SQLAlchemy 2.0 Async, Alembic)│ │ (Task Queue, Distributed Locks, SSE)│
└─────────────────────────────────┘ └────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────────────────┐
│                      Observability & Safety Mesh                       │
│  ┌──────────────────────┬──────────────────────┬─────────────────────┐ │
│  │ Prometheus & Alerts  │ Simulated Agent      │ Sample Target App   │ │
│  │ (Alertmanager HMAC)  │ (Allowlist, HMAC)    │ (Chaos Injection)   │ │
│  └──────────────────────┴──────────────────────┴─────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown
1. **Frontend Presentation (`frontend/`):** Next.js 16 (App Router), React 19, Tailwind CSS with dark navy design token palette (`#0B0F19`, `#111827`, `#1F2937`), Lucide icons, server-sent events (SSE) live updates.
2. **Backend API (`backend/app/`):** FastAPI async application exposing 129 endpoints across authentication, incidents, recoveries, policies, analytics, experiments, observability, and administration.
3. **Task & Event Broker (`backend/app/worker.py`):** Celery 5.4 distributed worker and Celery Beat scheduler backed by Redis 7.2.
4. **Relational Database (`backend/app/database.py`):** PostgreSQL 16 managed with SQLAlchemy 2.0 (asyncpg) and 9 sequential Alembic migrations.
5. **Observability Stack (`monitoring/`):** Prometheus (metrics scraping), Alertmanager (alert routing and HMAC webhook dispatch), Grafana (visualization), OpenTelemetry Collector, and Jaeger (distributed tracing).
6. **Simulated Infrastructure Agent (`backend/app/services/recovery/executor.py`):** Cryptographically authenticated, allowlist-bounded simulation client (`SimulatedAgentClient`).

---

## 3. Subsystem Readiness Matrix

| Subsystem | Readiness Status | Implementation Reference | Validation Evidence |
| :--- | :---: | :--- | :--- |
| **Authentication & RBAC** | **VERIFIED** | `backend/app/api/routes/auth.py` | Argon2id hashing, JWT access/refresh rotation, viewer/operator/admin checks passing. |
| **Alert Ingestion** | **VERIFIED** | `backend/app/api/routes/alerts.py` | HMAC-SHA256 signature verification, deduplication, automatic incident creation. |
| **Incident Lifecycle FSM** | **VERIFIED** | `backend/app/services/incident/` | Finite State Machine (`investigating` $\to$ `recovering` $\to$ `resolved` / `escalated`). |
| **AI Root Cause Diagnosis** | **VERIFIED** | `backend/app/services/ai/` | Google Gemini API integration with zero-downtime deterministic heuristic fallback. |
| **Recovery Policy Engine** | **VERIFIED** | `backend/app/services/recovery/policy_engine.py` | Allowlist action matching, blast-radius checks, mandatory human-in-the-loop approval. |
| **Simulation Recovery Execution** | **VERIFIED** | `backend/app/services/recovery/executor.py` | `SimulatedAgentClient` generates SHA-256 evidence receipts; zero host shell execution. |
| **Post-Recovery Verification** | **VERIFIED** | `backend/app/services/recovery/verifier.py` | Probes service error rate and latency; rejects false recoveries; transitions to escalated on failure. |
| **Audit & Event Logging** | **VERIFIED** | `backend/app/models/` | Append-only audit logs recording actor, action, resource, timestamp, and metadata. |
| **Experimentation & Benchmarking** | **VERIFIED** | `backend/app/services/experiment/` | Monte Carlo evaluation across S1–S5 scenarios, seed determinism, additive outage formula. |
| **Reporting Engine** | **VERIFIED** | `backend/app/api/routes/experiments.py` | JSON audit dumps and PDF summary generation using ReportLab. |

---

## 4. Quality Gate Summary

All automated quality gates have been executed against the codebase:

```
[Quality Gate Execution]
- Backend Pytest Suite:          340 passed, 0 failed, 19 warnings (172.82s)
- Python Syntax / Bytecode:      100% clean (backend/app/ compileall succeeded)
- Frontend TypeScript:           100% clean (tsc --noEmit: 0 errors)
- Frontend ESLint:               100% clean (eslint .: 0 errors)
- Next.js Production Build:      100% clean (next build: 5 static/dynamic routes compiled)
- Docker Compose Validation:     14 services verified (docker-compose.yml, docker-compose.dev.yml)
- Security & Secrets Audit:      100% clean (no exposed keys, passwords, or tokens staged)
```

---

## 5. Simulation vs Real Infrastructure Classification

To guarantee research integrity and deployment safety, all operations are classified:

| Operation Category | Classification | Reality Disclosure |
| :--- | :---: | :--- |
| **API Endpoints & Routing** | **GENUINE** | Real HTTP requests handled by FastAPI server. |
| **Database Transactions** | **GENUINE** | Real PostgreSQL transactions, schema migrations, and indexing. |
| **Authentication & RBAC** | **GENUINE** | Real Argon2id password hashing and cryptographic JWT signature validation. |
| **Background Task Queue** | **GENUINE** | Real Celery worker processing tasks over Redis broker. |
| **Alert Webhook Handling** | **GENUINE** | Real HMAC-SHA256 signature verification and payload deserialization. |
| **Report Generation** | **GENUINE** | Real PDF and JSON file generation written to disk/stream. |
| **Chaos Fault Injection** | **GENUINE** | Real HTTP faults injected into running `sample_app` microservice. |
| **Container Restart Action** | **SIMULATED** | State-machine simulated by `SimulatedAgentClient`; Docker daemon not touched. |
| **Worker Pool Recycling Action**| **SIMULATED** | State-machine simulated by `SimulatedAgentClient`; host processes not touched. |
| **Service Scaling Action** | **SIMULATED** | State-machine simulated by `SimulatedAgentClient`; cloud cluster not touched. |
| **Benchmark Outage Measurements**| **SIMULATED / CALCULATED** | Derived from deterministic seed-based PRNG modeling service degradation and restoration. |

---

## 6. Pilot Packaging Checklist

The Release Candidate includes all documentation required for a successful evaluator pilot:
- [SYSTEM_INSTALLATION_GUIDE.md](file:///c:/Users/aksha/Desktop/auto%20heal/SYSTEM_INSTALLATION_GUIDE.md): Clean-room local installation commands and prerequisites.
- [CONFIGURATION_GUIDE.md](file:///c:/Users/aksha/Desktop/auto%20heal/CONFIGURATION_GUIDE.md): Complete environment variable dictionary and safety locks.
- [USER_OPERATION_GUIDE.md](file:///c:/Users/aksha/Desktop/auto%20heal/USER_OPERATION_GUIDE.md): UI navigation and operational operator workflows.
- [INCIDENT_DEMONSTRATION_GUIDE.md](file:///c:/Users/aksha/Desktop/auto%20heal/INCIDENT_DEMONSTRATION_GUIDE.md): Reproducible chaos injection and recovery walkthrough.
- [SECURITY_AND_RECOVERY_SAFETY.md](file:///c:/Users/aksha/Desktop/auto%20heal/SECURITY_AND_RECOVERY_SAFETY.md): Threat model, allowlists, and cryptographic guarantees.
- [TROUBLESHOOTING_GUIDE.md](file:///c:/Users/aksha/Desktop/auto%20heal/TROUBLESHOOTING_GUIDE.md): Common error recovery, diagnostics, and log collection.
- [RELEASE_KNOWN_LIMITATIONS.md](file:///c:/Users/aksha/Desktop/auto%20heal/RELEASE_KNOWN_LIMITATIONS.md): Transparent disclosure of research and simulation boundaries.
- [PHASE_15_ACCEPTANCE_REPORT.md](file:///c:/Users/aksha/Desktop/auto%20heal/PHASE_15_ACCEPTANCE_REPORT.md): Formal acceptance audit across 14 dimensions.

---

## 7. Release Recommendation

AutoHeal DevOps v0.1.0-rc1 meets all criteria for a **Controlled Pilot Release Candidate**. It is ready for deployment in local, sandbox, and evaluator environments under `RECOVERY_SIMULATION_MODE=true`. It is **not** approved or configured for autonomous real-world infrastructure remediation.
