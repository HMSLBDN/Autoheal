# AutoHeal DevOps — Phase 19 Staging & Production Runbook
## Comprehensive Deployment, Governance, and Operations Manual

**Repository:** [https://github.com/HMSLBDN/Autoheal.git](https://github.com/HMSLBDN/Autoheal.git)  
**Branch:** `main`  
**Phase:** Phase 19 (Planning, Runbook & Operational Readiness)  
**Safety Mandate:** `RECOVERY_SIMULATION_MODE=true` (Active Default Hard Lock)  
**Target Environments:** Staging Mesh (`autoheal_test_network`) & Production Stack (`autoheal_network`)  
**Document Classification:** Operational Runbook & Production Readiness Evaluation  

---

## 1. Unresolved Validation Issues & Root-Cause Audit

Prior to formalizing the staging pilot, an audit of prior phases was conducted to identify open technical debts, environmental couplings, and test failure patterns:

### 1.1 The Phase 17 HTTP 503 Verification Failure
* **Symptom:** During bulk regression execution, `tests/test_phase17_integration.py::test_failed_verification_when_service_remains_degraded` failed with:
  ```text
  AssertionError: Expected HTTP 503 from degraded test service, got 200
  assert 200 == 503
  ```
* **Root Cause Analysis:**
  1. `test_phase17_integration.py` was authored as a **staged live-service integration test**. It queries the live running container at `http://autoheal_test_service:8080/health`.
  2. The test file does not control the container's state programmatically within a test fixture; instead, it relies on an external operator executing manual chaos curl requests (`POST /chaos/degrade`) *prior* to running the test.
  3. Because Phase 17 Stage B had restored the container (`POST /chaos/restore`) to a healthy state (HTTP 200), executing Test 1 in regression mode without the manual pre-flight degradation command encountered a healthy container, triggering the assertion failure.
  4. In contrast, Phase 18 (`tests/test_phase18_e2e_validation.py`) achieved full hermetic test isolation by testing both degraded (503) and healthy (200) pathways independently using application-level test client overrides.
* **Remediation Plan for Staging Pilot:**
  - Standardize `test_phase17_integration.py` with an async pytest fixture that automatically sends `/chaos/degrade` before Test 1 and cleans up with `/chaos/restore` after Test 2.
  - Require all automated CI/CD pipeline runs to use hermetic fixtures rather than expecting pre-existing container state.

### 1.2 Other Identified Operational Gaps
| Issue Identifier | Component | Current State | Required Staging Resolution |
| :--- | :--- | :--- | :--- |
| **GAP-01** | Prometheus Scrapes | Prometheus is on `autoheal_network`; test containers are on `autoheal_test_network`. | Maintain network isolation; route scrape telemetry via synthetic webhooks or an explicit scrape proxy. |
| **GAP-02** | Celery Recovery Queue | `tasks/recovery.py` has no automatic Celery dispatch triggers. | Maintain manual/API approval triggers; wire Celery worker queue metrics in staging observability. |
| **GAP-03** | Secret Generation | Compose files provide default dev secrets if environment variables are unset. | Enforce strict env-var validation: fail container startup if secrets are defaults or < 32 characters. |

---

## 2. Production Architecture and Deployment Topology

AutoHeal DevOps enforces a **Dual-Network Zero-Trust Architecture** separating application microservices from recovery executors and Docker sockets.

```
+========================================================================================+
|                              HOST INFRASTRUCTURE (DOCKER)                              |
+========================================================================================+
|                                                                                        |
|   +--------------------------------------------------------------------------------+   |
|   |                  PRODUCTION NETWORK (`autoheal_network` - Bridge)              |   |
|   |                                                                                |   |
|   |  +-------------------+        +-------------------+        +----------------+  |   |
|   |  |     Frontend      |  HTTP  |      Backend      |  mTLS  |   Prometheus   |  |   |
|   |  | (Next.js 16/R19)  |------->|     (FastAPI)     |<-------|   (v2.51.0)    |  |   |
|   |  |     Port: 3000    |        |     Port: 8000    |        |   Port: 9090   |  |   |
|   |  +-------------------+        +---------+---------+        +--------+-------+  |   |
|   |                                         |                           |          |   |
|   |        +--------------------------------+                  Firing   |          |   |
|   |        | Async SQLAlchemy (asyncpg)                        Alerts   |          |   |
|   |        v                                                            v          |   |
|   |  +-------------------+        +-------------------+        +----------------+  |   |
|   |  |    PostgreSQL     |        |   Redis Queue     |  HMAC  |  Alertmanager  |  |   |
|   |  |   (v16 Alpine)    |        |   (v7 Alpine)     |<-------|   (v0.27.0)    |  |   |
|   |  |    Port: 5432     |        |    Port: 6379     |        |   Port: 9093   |  |   |
|   |  +-------------------+        +---------+---------+        +----------------+  |   |
|   |                                         |                                      |   |
|   |                                         | Task Dispatch                        |   |
|   |                                         v                                      |   |
|   |                               +-------------------+                            |   |
|   |                               |   Celery Worker   |                            |   |
|   |                               |  & Beat Scheduler |                            |   |
|   |                               +-------------------+                            |   |
|   +--------------------------------------------------------------------------------+   |
|                                                                                        |
|   +--------------------------------------------------------------------------------+   |
|   |              AIR-GAPPED TEST MESH (`autoheal_test_network` - Internal)         |   |
|   |                                                                                |   |
|   |  +-----------------------+      mTLS (8443)      +--------------------------+  |   |
|   |  | autoheal_socket_proxy |<----------------------|  autoheal_docker_agent   |  |   |
|   |  | (NGINX L7 / Read-Only)|                       | (Restricted / Unpriv 1000) |  |   |
|   |  +-----------+-----------+                       +------------+-------------+  |   |
|   |              |                                                |                |   |
|   |              | /var/run/docker.sock                           | Probes Health  |   |
|   |              v                                                v                |   |
|   |  [Host Docker Daemon]                            +--------------------------+  |   |
|   |  (Restarts only allowlisted targets)             |  autoheal_test_service   |  |   |
|   |                                                  |   (Mock Service :8080)   |  |   |
|   |                                                  +--------------------------+  |   |
|   +--------------------------------------------------------------------------------+   |
|                                                                                        |
+========================================================================================+
```

### Architectural Isolation Principles:
1. **Zero Socket Access to Core Services:** `/var/run/docker.sock` is mounted strictly into `autoheal_socket_proxy`. Frontend, FastAPI Backend, Celery, and DB containers have zero socket visibility.
2. **Proxy Whitelisting:** `autoheal_socket_proxy` runs as unprivileged user `101:101`, read-only rootfs, drops all capabilities (`cap_drop: ALL`), and restricts Docker API endpoints to container restart filters.
3. **Internal Air-Gap:** `autoheal_test_network` has `internal: true`, preventing inbound or outbound traffic to the public internet.

---

## 3. Environment Configuration & Secret Management

### 3.1 Mandatory Secret Specifications
All production secrets must meet enterprise entropy standards (minimum 32 characters, high cryptographic entropy):

| Secret Name | Required Length | Rotation Interval | Purpose |
| :--- | :---: | :---: | :--- |
| `SECRET_KEY` | $\ge 32$ chars | 90 days | Signs JWT access tokens and state machine hashes |
| `ALERTMANAGER_WEBHOOK_SECRET` | $\ge 32$ chars | 90 days | Validates HMAC-SHA256 signatures from Alertmanager |
| `POSTGRES_PASSWORD` | $\ge 24$ chars | 180 days | Secures PostgreSQL root & application credentials |
| `REDIS_PASSWORD` | $\ge 24$ chars | 180 days | Authenticates Celery & Redis operations |
| `DOCKER_AGENT_SECRET_KEY` | $\ge 32$ chars | 90 days | Generates HMAC-SHA256 signatures for agent API requests |

### 3.2 Secret Management Strategy
1. **No Secrets in Source:** `.env` files are strictly excluded via `.gitignore` and `.dockerignore`.
2. **Environment Variable Injection:** In staging, secrets are sourced from Docker secrets or an encrypted `.env.staging` file injected at runtime.
3. **Production Vault:** In cloud production, secrets must be loaded from HashiCorp Vault or AWS Secrets Manager.

---

## 4. Database and Redis Setup, Backup, and Recovery

### 4.1 PostgreSQL Architecture (v16 Alpine)
- **Driver:** Async SQLAlchemy with `asyncpg` connection pool.
- **Connection Pool Configuration:**
  - `pool_size`: 20 connections per container.
  - `max_overflow`: 10 connections.
  - `pool_timeout`: 30 seconds.
  - `pool_recycle`: 1800 seconds (avoids stale server-side drops).
- **Persistence:** Docker named volume `pgdata` mapped to `/var/lib/postgresql/data`.

### 4.2 Automated Backup Runbook
Execute automated daily backup using the provided script:
```powershell
# Run manual verified backup
python scripts/validate_postgres_backup.py
```
- **Backup Location:** `backups/postgres_YYYYMMDD_HHMMSS.sql.gz`
- **RPO Target:** $< 1$ hour.
- **RTO Target:** $< 15$ minutes.

### 4.3 Redis State Management (v7 Alpine)
- **AOF Persistence:** `--appendonly yes` enabled with `appendfsync everysec`.
- **Memory Policy:** `maxmemory 512mb` with `maxmemory-policy noeviction` for task queues.
- **Persistence:** Volume `redisdata` mapped to `/data`.

---

## 5. Prometheus, Alertmanager, and Grafana Configuration

### 5.1 Prometheus Configuration (`monitoring/prometheus.yml`)
- **Scrape Interval:** 15 seconds.
- **Rule Evaluation Interval:** 15 seconds.
- **Alert Rules (`monitoring/alerts.yml`):**
  - `HighErrorRate`: Fires when `rate(http_requests_total{status=~"5.."}[1m]) / rate(http_requests_total[1m]) > 0.05` for 30 seconds.
  - `ServiceDegraded`: Fires when service `/health` probe returns non-200 for 15 seconds.

### 5.2 Alertmanager Webhook Ingestion (`monitoring/alertmanager.yml`)
- **Receiver:** `autoheal-backend-webhook`.
- **URL:** `http://autoheal-api:8000/api/v1/alerts/webhook`.
- **Security:** HMAC-SHA256 signature generated in header `X-Alertmanager-HMAC-SHA256`.

---

## 6. Docker Agent Security & Restricted Recovery Architecture

### 6.1 Defense-in-Depth Comparison Matrix: Simulated vs Real Recovery

| Dimension | Simulated Recovery (`SIMULATED`) | Real Docker Recovery (`RESTRICTED_AGENT`) |
| :--- | :--- | :--- |
| **`RECOVERY_SIMULATION_MODE`** | **`true` (Mandatory for Pilot)** | `false` (Strictly prohibited for pilot) |
| **`RESTRICTED_DOCKER_AGENT_ENABLED`**| `false` | `true` |
| **Execution Path** | `RecoveryExecutor._execute_simulated()` | `RestrictedDockerAgentClient.restart_container()`|
| **Docker API Calls** | **Zero** (no socket communication) | Restricted restart via `autoheal_socket_proxy` |
| **Output Receipt** | `[AGENT_EXECUTION_RECEIPT] MODE: SIMULATED` | `[AGENT_EXECUTION_RECEIPT] AGENT_ID: docker-agent-...` |
| **Permitted Targets** | Any internal simulated service model | Strictly `autoheal_test_service` |
| **Reversibility** | Instantaneous mock transition | Container process stop & start cycle |

### 6.2 Agent Security Controls
1. **Server-Side Allowlist:** The agent parses container names and strictly matches against `DOCKER_AGENT_APPROVED_CONTAINERS`. Any command against core containers (`autoheal_backend`, `db`, `redis`) is rejected with HTTP 403.
2. **Replay Protection:** Nonce cache with sliding 60-second window. Reused nonces trigger immediate HTTP 401.
3. **mTLS Communication:** Client certificates validated against tenant CA at NGINX proxy.

---

## 7. Authentication, RBAC, and Operator Approval Governance

### 7.1 Role-Based Access Control (RBAC) Matrix
| Resource / Action | Viewer | Operator | Admin |
| :--- | :---: | :---: | :---: |
| View Incidents & Analytics | Read-Only | Read-Only | Full Access |
| View Service Health & Logs | Read-Only | Read-Only | Full Access |
| Approve / Reject Recovery Actions | **Denied (403)** | **Permitted (200)** | **Permitted (200)** |
| Execute Recovery (`POST /execute`) | **Denied (403)** | **Permitted (200)** | **Permitted (200)** |
| Modify Recovery Policies | Denied (403) | Denied (403) | **Permitted (200)** |
| Override Incident Resolution Guard | Denied (403) | **Permitted (Sign-off)** | **Permitted (Sign-off)** |

### 7.2 Service-Layer Dual Guard Governance
As validated in Phase 18, unapproved actions cannot be executed from any layer:
- **API Router Guard:** `routes/recoveries.py#L286` blocks `approval_required=True` with `HTTP 400 Bad Request`.
- **Service Layer Guard:** `executor.py#L82` raises `ValueError` if `approval_required=True and status != "approved"`.
- **State Machine Guard:** `state_machine.py#L134` raises `InvalidIncidentTransitionError` if attempting resolution without verified recovery or explicit operator justification ($\ge 8$ chars).

---

## 8. Incident Lifecycle & Two-Stage Health Verification

### 8.1 Verification Protocol
```
[Recovery Action Dispatched]
           │
           ▼
[Stage 1: Execution Handshake]
  ├── Simulated Mode: Generate mocked execution receipt
  └── Real Mode: Agent issues container restart
           │
           ▼
[Stage 2: Independent Application Health Probe]
  ├── PostRecoveryVerifier probes target HTTP health endpoint
  ├── Scenario A: Endpoint returns HTTP 503
  │     ├── verification = 'failed'
  │     ├── evidence_classification = 'VERIFICATION_FAILED'
  │     └── incident.status remains 'investigating' (Never falsely resolved)
  └── Scenario B: Endpoint returns HTTP 200
        ├── verification = 'passed'
        ├── evidence_classification = 'HEALTH_VERIFIED'
        └── incident.status transitions to 'resolved'
```

---

## 9. Logging, Audit Trails, and Observability

1. **Tamper-Evident Incident Audit Trail:**
   - Every lifecycle transition writes an immutable `IncidentTransition` record with UUID, `actor_id`, `actor_email`, `actor_role`, `from_state`, `to_state`, and `reason`.
2. **OpenTelemetry & Jaeger Tracing:**
   - Distributed trace spans capture webhook ingestion latency, AI diagnosis model invocation, and database queries.
3. **Structured JSON Logs:**
   - All backend application logs format with ISO 8601 UTC timestamps, level, correlation ID, and module name.

---

## 10. CI/CD Pipeline & Quality Gates

The following automated gates must pass before any code reaches staging:

```
[Git Push / PR] ──> [Gate 1: Static Analysis]
                           ├── Python Syntax: python -m py_compile
                           ├── TypeScript: pnpm exec tsc --noEmit
                           └── ESLint: pnpm run lint
                                 │
                                 ▼
                     [Gate 2: Unit & Policy Tests]
                           ├── backend/tests/test_auth.py
                           ├── backend/tests/test_recovery_engine.py
                           └── backend/tests/test_performance_reliability.py
                                 │
                                 ▼
                     [Gate 3: Ephemeral E2E Validation]
                           └── autoheal-test-runner: pytest tests/test_phase18_e2e_validation.py
                                 │
                                 ▼
                     [Gate 4: Compose Specification Audit]
                           └── docker compose config --quiet
```

---

## 11. Deployment Rollback & Disaster Recovery

### 11.1 Rollback Procedures
In the event of an unhealthy deployment during staging rollout:
1. **Immediate Frontend/Backend Stop:**
   ```bash
   docker compose stop frontend backend celery_worker celery_beat
   ```
2. **Checkout Prior Stable Release Tag:**
   ```bash
   git checkout tags/v1.0.0-rc1
   ```
3. **Rebuild and Start:**
   ```bash
   docker compose up -d --build frontend backend celery_worker celery_beat
   ```
4. **Database Rollback:** If Alembic migrations were applied:
   ```bash
   docker compose exec backend alembic downgrade -1
   ```

---

## 12. Security Testing & Operational Acceptance Criteria

Before staging pilot sign-off, verify:
- [x] OWASP Top 10 compliance (SQL injection prevented via SQLAlchemy parameterized queries; XSS prevented via React JSX auto-escaping).
- [x] Zero plain-text credentials in logs or responses.
- [x] Single-use Server-Sent Events ticket issuance with 60-second TTL.
- [x] Rate limiting on authentication endpoints (5 failed login attempts $\to$ 15-minute lockout).

---

## 13. Staging Pilot Demonstration Procedure

Follow this controlled step-by-step procedure to demonstrate the platform to stakeholders:

### Step 1: Pre-Demo Status Check
Confirm `autoheal_test_service` is running and healthy:
```bash
docker ps --filter "name=autoheal_test_service"
```

### Step 2: Ingest Synthetic Degradation Alert
Send an authenticated synthetic alert payload to the backend:
```bash
python scripts/local_demo_runner.py --scenario high_error_rate --mode simulated
```

### Step 3: Observe Real-Time Dashboard
1. Open the dashboard at `http://localhost:3000`.
2. Observe the new Incident appear in the Incident Center in `investigating` status via SSE.
3. Observe AI diagnosis root cause analysis: `"Connection pool exhaustion under simulated load"`.
4. Observe proposed action in Recovery Center: `"restart_service"` with `status: pending_approval`.

### Step 4: Governance Approval Gate
1. Log in as an `operator` role.
2. Click **Approve Recovery Action**.
3. Confirm status transitions to `approved`.

### Step 5: Simulated Execution & Verification
1. Click **Execute Action**.
2. Inspect the generated execution receipt:
   ```text
   [AGENT_EXECUTION_RECEIPT]
   MODE: SIMULATED
   ACTION: restart_service
   STATUS: COMPLETED
   ```
3. Observe post-recovery verification query `http://autoheal_test_service:8080/health`.
4. When healthy, incident automatically resolves with audit justification.

---

## 14. Production Readiness Checklist

| Category | Readiness Item | Verified State | Status |
| :--- | :--- | :--- | :---: |
| **Safety** | Simulation mode hard-locked default | `RECOVERY_SIMULATION_MODE=true` | **READY** |
| **Security** | Zero Docker socket exposure to web containers | Socket exclusive to `autoheal_socket_proxy` | **READY** |
| **Security** | Service-layer operator approval guard | Implemented in `RecoveryExecutor` | **READY** |
| **Reliability** | End-to-end integration suite | 13/13 Phase 18 tests passing | **READY** |
| **Reliability** | Idempotency benchmark performance | 0.51 ms execution duration | **READY** |
| **Code Quality**| TypeScript & ESLint validation | 0 errors across frontend codebase | **READY** |
| **Secrets** | Production secret enforcement | Minimum 32-character requirement | **READY** |
| **Observability**| Audit trail immutability | `IncidentTransition` records enforced | **READY** |

---

## 15. Operational Risk Register

| Risk ID | Threat Description | Probability | Impact | Mitigation Strategy | Owner |
| :---: | :--- | :---: | :---: | :--- | :---: |
| **RSK-01** | Accidental execution of real recovery commands on production containers | Very Low | Critical | Hard-locked `RECOVERY_SIMULATION_MODE=true` default; server-side container allowlists in agent | SRE Lead |
| **RSK-02** | Stale test state in external containers causing integration test failure | Medium | Low | Refactor `test_phase17_integration.py` to use hermetic teardown fixtures | QA Lead |
| **RSK-03** | Operator token leakage enabling unauthorized recovery execution | Low | High | 15-minute JWT expiration; HttpOnly refresh cookies; single-use SSE tickets | SecOps |
| **RSK-04** | AI diagnosis API rate limit exhaustion during alert storm | Medium | Medium | Deterministic rule-based fallback engine executes automatically on API timeout | Backend Lead |

---

## 16. Remaining Validation Tasks Prior to Staging Cutover

1. **Refactor Phase 17 Test Harness:**
   - Update `test_phase17_integration.py` to hermetically inject `/chaos/degrade` and `/chaos/restore` via pytest fixtures rather than expecting manual container states.
2. **Prometheus Telemetry Bridge Test:**
   - Conduct a shadow scrape test verifying Prometheus metric collection without connecting test networks to production networks.
3. **Stakeholder Pilot Walkthrough:**
   - Execute the Staging Pilot Demonstration Procedure (Section 13) with the operations team under simulated mode.
