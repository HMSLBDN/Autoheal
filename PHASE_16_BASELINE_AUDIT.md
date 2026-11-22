# Phase 16 Baseline Audit — Controlled Real Infrastructure Integration

**Document Version:** 1.0.0  
**Phase:** Phase 16 — Controlled Real Infrastructure Integration & Production Readiness  
**Target Repository:** [https://github.com/HMSLBDN/Autoheal.git](https://github.com/HMSLBDN/Autoheal.git)  
**Branch:** `main`  
**Baseline Commit:** `33d58d9ea164e70c5732fce15200f888b477af12`  
**Current Release Tag:** `v0.1.0-rc1`  
**Audit Date:** November 22, 2026  
**Auditor:** AutoHeal Engineering & Security Architecture Team  

---

## 1. Git State and Baseline Verification

- **Branch:** `main`
- **Head Commit:** `33d58d9ea164e70c5732fce15200f888b477af12`
- **Commit Message:** `docs(phase-15): add release candidate documentation, pilot package, and acceptance report`
- **Working Tree State:** Completely clean (`nothing to commit, working tree clean`).
- **Remote Synchronization:** Local `main` is up to date with `origin/main`.
- **CI Baseline:** GitHub Actions Run [44998251739](https://github.com/HMSLBDN/Autoheal/actions/runs/44998251739) passed (`completed` / `success` across all 4 jobs: Docker Validation, Backend Pytest, Security Scan, Frontend Build).
- **Release Documentation:** All 9 Phase 15 release candidate documents are tracked, validated, and published.

---

## 2. Existing Architecture Overview

AutoHeal DevOps operates as a modular, asynchronous platform comprising:

1. **Presentation Layer (`frontend/`):** Next.js 16 (React 19, Tailwind CSS, Lucide icons, Dark Navy theme) with Server-Sent Events (SSE) for real-time incident status streaming.
2. **Application Core (`backend/app/`):** FastAPI async application with 129 REST routes across authentication, incidents, recoveries, policies, analytics, experiments, observability, and administrative functions.
3. **Task & Event Broker (`backend/app/worker.py`):** Celery 5.4 distributed worker and Celery Beat scheduler backed by Redis 7.2.
4. **Relational Persistence (`backend/app/database.py`):** PostgreSQL 16 managed via SQLAlchemy 2.0 (asyncpg) with 9 sequential Alembic migrations.
5. **Observability Mesh (`monitoring/`):** Prometheus (time-series scraping), Alertmanager (HMAC-signed webhook dispatch), Grafana (dashboards), OpenTelemetry Collector, Jaeger, Node Exporter, and cAdvisor.
6. **Recovery Engine (`backend/app/services/recovery/`):**
   - `orchestrator.py`: Finite State Machine governing recovery states (`pending_approval` $\to$ `approved` $\to$ `executing` $\to$ `completed` $\to$ `verified` / `failed`).
   - `policy_engine.py`: Evaluates cooldown periods, maximum retries (default: 3), blast radius, and target service environment.
   - `registry.py`: Allowlist definitions for permissible actions (`restart_container`, `restart_pool`, `scale_service`).
   - `executor.py`: Orchestrates action execution and dispatches requests to an `InfrastructureAgentClient`.
   - `verifier.py`: `PostRecoveryVerifier` evaluates post-action telemetry against SLO thresholds.

---

## 3. Current Recovery Execution Flow & Simulation Safeguards

### Current Execution Path (Phase 15 State)
```
Operator Approves Action
       │ (POST /api/v1/recoveries/{id}/approve)
       ▼
RecoveryExecutor.execute_recovery()
       │
       ├─► Validates action against is_action_allowed(action)
       ├─► Evaluates policy constraints via policy_engine.evaluate_policy()
       ├─► Transitions Recovery state to 'executing'
       │
       ▼
Dispatches ActionRequest to self.agent_client
       │ (self.agent_client = SimulatedAgentClient())
       ▼
SimulatedAgentClient.dispatch_action()
       │
       ├─► Verifies HMAC-SHA256 signature and checks nonce replay cache
       ├─► Validates action type and parameters against validate_agent_action()
       ├─► Non-blocking sleep (0.05s) to simulate execution duration
       ├─► Generates synthetic stdout text string
       ├─► Calculates SHA-256 evidence receipt hash
       └─► Returns ActionResult(status=SUCCESS, exit_code=0)
       │
       ▼
PostRecoveryVerifier.verify_recovery()
       │
       ├─► Injects simulated post-telemetry (error_rate = 0.02%, latency = 115ms)
       ├─► Compares against incident threshold
       ├─► Transitions incident status to 'resolved'
       └─► Records immutable AuditLog and IncidentEvent
```

### Existing Safeguards
- **Mandatory Simulation Hard Lock:** `RECOVERY_SIMULATION_MODE=true` is defined in `backend/app/config.py` and locked in `.env`.
- **Zero Socket Exposure:** Neither `docker-compose.yml` nor `docker-compose.dev.yml` mounts `/var/run/docker.sock` into any application container.
- **No Arbitrary Shell Invocations:** The backend contains zero calls to `os.system()`, `subprocess.Popen(shell=True)`, or raw shell wrappers.
- **HMAC Request Envelopes:** `ActionRequest` requires cryptographic HMAC-SHA256 signing, a unique UUID `nonce`, and a UTC timestamp with a 300-second maximum drift window.

---

## 4. Missing Real-Infrastructure Capabilities (Code vs Documentation Gap)

An exhaustive code audit reveals several critical capabilities documented in prior theoretical reports that are **not** genuinely implemented in code:

| Component / Feature | Documented Status | Actual Implementation Reality | Audit Gap |
| :--- | :--- | :--- | :--- |
| **Standalone Docker Agent Daemon** | Mentioned in Phase 10 guides | **Does not exist.** No standalone agent server/daemon binary or container exists. | **CRITICAL GAP:** Only `SimulatedAgentClient` runs in-process. |
| **Live Docker API Integration** | Documented in `docker_adapter.py` | **Stubbed.** `RestrictedDockerAdapter` returns hardcoded dictionaries even if `simulation_mode=False`. | **CRITICAL GAP:** No `docker` SDK or Docker Engine API calls exist. |
| **Remote Agent Server API** | Described in `client.py` docstrings | **Client stub only.** `RemoteAgentClient` exists as an HTTP client, but no daemon listens for its requests. | **CRITICAL GAP:** No receiving server implementation exists. |
| **Dedicated Test Application** | Referenced in demonstration guides | `sample_app` exists for HTTP chaos, but has no dedicated Docker lifecycle control. | **GAP:** No dedicated isolated test container for real restarts. |
| **Isolated Test Network Mesh** | Described in security guides | Not defined as an isolated Docker network separate from core stack. | **GAP:** Needs dedicated bridge network with zero backend socket access. |
| **Real Health Verification Probes** | Described in verifier docs | `PostRecoveryVerifier` accepts `simulated_healthy=True` and updates DB attributes; does not make actual network HTTP probes. | **GAP:** Needs genuine HTTP probing against test container endpoint. |

---

## 5. Security Gaps and Real Infrastructure Risks

Transitioning from simulation to real Docker infrastructure introduces substantial security and operational hazards:

### 1. The Docker Daemon Socket Hazard (`/var/run/docker.sock`)
- **Risk:** The Docker daemon API is effectively equivalent to root access on the host system. Exposing `/var/run/docker.sock` to the web-facing FastAPI backend would mean any backend Remote Code Execution (RCE) or Server-Side Request Forgery (SSRF) could compromise the entire host machine.
- **Safeguard:** FastAPI must **NEVER** mount or access `/var/run/docker.sock`. Docker daemon access must be restricted to a standalone, sandboxed agent running in a separate network.

### 2. Uncontrolled Container Blast Radius
- **Risk:** If an agent has generic Docker restart capabilities, a compromised or misconfigured policy could restart critical production containers (`db`, `redis`, `backend`, `prometheus`), causing an infrastructure-wide outage.
- **Safeguard:** The agent must enforce a strict, server-side allowlist of permitted container identifiers. It must explicitly reject any operation targeting unapproved services, system containers, or database volumes.

### 3. Argument Injection & Metacharacter Hazards
- **Risk:** User-supplied strings passed into Docker command lines could trigger shell metacharacter execution (`;`, `|`, `&&`, `$()`).
- **Safeguard:** The agent must communicate via the typed Docker Engine HTTP socket (or SDK) using structured JSON/API parameters, **never** via shell subprocesses. All container names must match strict regex `^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$`.

### 4. Split-Brain & Premature Resolution Risk
- **Risk:** A container restart may return exit code 0 (`container restart succeeded`), while the application inside remains in a crash loop or failed initialization state.
- **Safeguard:** Container restart success must **never** be equated with recovery resolution. The recovery workflow must require independent, two-stage verification:
  1. Stage 1: Container state inspection (Agent confirms container status `running` and health status `healthy`).
  2. Stage 2: Application health probe (HTTP probe to `/health` confirming HTTP 200 and valid JSON payload).

---

## 6. Recommended Phase 16 Architecture

To address all identified gaps safely and securely, Phase 16 must implement:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AutoHeal Control Plane                          │
│                                                                        │
│   FastAPI Application Core (NO DOCKER SOCKET)                          │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │ RecoveryExecutor                                                │  │
│   │  ├─► Evaluates Policy & RBAC (Operator/Admin required)          │  │
│   │  ├─► Generates HMAC-SHA256 signed ActionRequest with Nonce      │  │
│   │  └─► Dispatches via DockerAgentClient (HTTP over internal net)  │  │
│   └────────────────────────────────┬────────────────────────────────┘  │
└────────────────────────────────────┼───────────────────────────────────┘
                                     │ Authenticated HTTP API
                                     │ (JSON / HMAC-SHA256 / Shared Secret)
┌────────────────────────────────────▼───────────────────────────────────┐
│              Dedicated Isolated Test Network Mesh                      │
│                   (autoheal_test_network)                              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Restricted Docker Recovery Agent (docker_agent)                  │  │
│  │                                                                  │  │
│  │  - Isolated container / process                                  │  │
│  │  - Authenticated REST API (port 8091)                            │  │
│  │  - Independent Server-Side Container Allowlist:                  │  │
│  │      * ONLY 'autoheal_test_service' permitted                    │  │
│  │      * REJECTS all other container names                         │  │
│  │  - Independent Server-Side Action Allowlist:                     │  │
│  │      * inspect_container, get_container_state                   │  │
│  │      * restart_container, verify_container_health                │  │
│  │  - Nonce Replay Cache (TTL: 300s) + Timestamp Drift Check (300s) │  │
│  │  - Docker Engine Socket Client (Least privilege boundary)        │  │
│  │  - Independent Application Health Prober (HTTP GET /health)      │  │
│  │  - Structured Audit Log & Prometheus Metrics (/metrics)          │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    │ Docker API Socket / Network Probe │
│                                    ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Dedicated Test Application Container (autoheal_test_service)     │  │
│  │                                                                  │  │
│  │  - Harmless Python/FastAPI microservice                          │  │
│  │  - Endpoints: GET /health, GET /status, POST /chaos/crash        │  │
│  │  - Zero access to AutoHeal databases, credentials, or core stack │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Baseline Audit Conclusions

1. **Safety Mode Verified:** The baseline is 100% compliant with simulation rules; no real infrastructure has been compromised.
2. **Missing Implementation Identified:** There was no running agent daemon or live Docker integration. Phase 16 must build the standalone restricted agent service from the ground up.
3. **Boundary Enforced:** The control plane (FastAPI) must remain strictly decoupled from the Docker socket.
4. **Isolated Test Scope:** Real Docker testing will be restricted exclusively to `autoheal_test_service` on `autoheal_test_network`.
