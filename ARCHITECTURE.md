# AutoHeal DevOps — Architecture & System Design Document

## 1. Architectural Overview

AutoHeal DevOps is an autonomous, policy-governed site reliability engineering (SRE) and self-healing platform. It continuously ingests system telemetry, detects SLO regressions, triggers AI-driven incident diagnosis, gates remediation actions with human-in-the-loop authorization, and safely executes simulated recovery workflows with post-recovery verification.

```
+---------------------------------------------------------------------------------------------------+
|                                      MONITORED INFRASTRUCTURE                                     |
|                                                                                                   |
|   +---------------------+   +---------------------+   +---------------------+   +-------------+   |
|   |    checkout-api     |   |    customer-web     |   |    payments-api     |   | cadvisor /  |   |
|   |     (Port 8080)     |   |     (Port 8081)     |   |     (Port 8082)     |   | node-exp    |   |
|   +----------+----------+   +----------+----------+   +----------+----------+   +------+------+   |
+--------------|-------------------------|-------------------------|---------------------|----------+
               | /metrics                | /metrics                | /metrics            | /metrics
               +-------------------------+------------+------------+---------------------+
                                                      |
                                                      v
                                        +---------------------------+
                                        |        Prometheus         |
                                        |    (Scrapes & Rules)      |
                                        +-------------+-------------+
                                                      | Firing Alert (SLO breach)
                                                      v
                                        +---------------------------+
                                        |       Alertmanager        |
                                        | (Grouping & Ingestion GW) |
                                        +-------------+-------------+
                                                      |
                                                      | Authenticated Webhook (HMAC / Bearer Token)
                                                      v
+---------------------------------------------------------------------------------------------------+
|                                         AUTOHEAL BACKEND                                          |
|                                                                                                   |
|   +-------------------------------------------------------------------------------------------+   |
|   | FastAPI Webhook Router (/api/v1/alerts/webhook)                                           |   |
|   |  - Token validation (HMAC SHA-256 or Bearer secret)                                       |   |
|   |  - Incident Deduplication: maps alerts to active service incidents                       |   |
|   |  - Persistent incident creation (PostgreSQL)                                              |   |
|   +---------------------------------------------+---------------------------------------------+   |
|                                                 |                                                 |
|          +--------------------------------------+--------------------------------------+          |
|          |                                      |                                      |          |
|          v                                      v                                      v          |
|   +---------------+                     +---------------+                      +---------------+  |
|   |  AI Diagnosis |                     |   Recovery    |                      | SSE Streaming |  |
|   |    Engine     |                     |    Engine     |                      |  Broadcaster  |  |
|   | (Gemini 1.5   |                     | (Allowlist    |                      | (Single-use   |  |
|   |  + Heuristic) |                     |  Simulation)  |                      |  SSE tickets) |  |
|   +---------------+                     +-------+-------+                      +-------+-------+  |
|                                                 |                                      |          |
|                                                 v                                      v          |
|                                         +---------------+                      +---------------+  |
|                                         | Restricted    |                      | Frontend Real-|  |
|                                         | Agent Client  |                      | Time Sync     |  |
|                                         +---------------+                      +---------------+  |
+-------------------------------------------------+-------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                   DATA STORAGE & ASYNC QUEUES                                     |
|                                                                                                   |
|   +---------------------------------------------+   +-----------------------------------------+   |
|   |                 PostgreSQL                  |   |                  Redis                  |   |
|   | - 16 relational tables with tenant scoping  |   | - Celery broker & result backend        |   |
|   | - Connection pooling (SQLAlchemy AsyncIO)   |   | - Token revocation list                 |   |
|   | - Alembic schema versioning                 |   | - TLS-encrypted transport               |   |
|   +---------------------------------------------+   +-----------------------------------------+   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Core Subsystems

### 2.1 Telemetry Collection & Monitoring Pipeline
1. **Scrape Engine**: Prometheus scrapes microservice telemetry at a 15-second interval across application endpoints (`/metrics`) and host exporters (`cadvisor:8080`, `node_exporter:9100`).
2. **SLO Alert Rules**: Prometheus evaluates alert rules defined in `monitoring/alerts.yml`:
   * `ServiceDown`: Fired when `up{job=~"checkout-api|customer-web|payments-api"} == 0` for $\ge 30\text{s}$.
   * `HighErrorRate`: Fired when 5xx error rate exceeds $1.5\%$ for $\ge 1\text{m}$.
   * `HighLatency`: Fired when P95 response time exceeds $500\text{ms}$ for $\ge 1\text{m}$.
   * `CPUSaturation`: Fired when process CPU exceeds $85\%$ for $\ge 2\text{m}$.
   * `MemoryLeakSuspected`: Fired when memory consumption exceeds $1.8\text{ GB}$ for $\ge 3\text{m}$.
3. **Alertmanager Webhook**: Active alerts are grouped and dispatched via HTTP POST to FastAPI `/api/v1/alerts/webhook` with HMAC SHA-256 or Bearer authentication. This endpoint is strictly a server-to-server interface; the Next.js frontend never invokes or handles webhook secrets, which remain exclusively server-side.

### 2.2 Incident Management & Deduplication
* **Deterministic Incident ID Generation**: Incidents receive monotonic identifiers (e.g., `INC-1070`).
* **Active Incident Matching**: When a firing alert arrives, FastAPI queries for existing active incidents on the service (`status in ['open', 'investigating', 'recovering']`).
* **Deduplication**: If an active incident exists, it is updated and an `Alert Re-triggered` event is appended. New incidents are only created if no active incident exists.
* **Auto-Resolution**: When Prometheus marks an alert resolved, Alertmanager delivers a `status: resolved` payload. FastAPI sets `status = 'resolved'`, records `resolved_at`, and appends an audit entry.

### 2.3 AI Diagnosis Engine
* **Input Sanitization**: Untrusted alert labels, descriptions, and log fragments are sanitized using regex filtering (`PROMPT_INJECTION_PATTERN`) and truncated to 500 characters.
* **Primary Engine (Google Gemini 1.5 Pro)**: Generates structured JSON post-mortems via the Generative Language API.
* **Action Allowlist Validation**: The proposed `recommended_action` is validated against `APPROVED_RECOVERY_ACTIONS` (`restart_service`, `clear_cache`, `scale_service`, `restore_health`, `rollback_release`). Unapproved actions are rejected and replaced with safe defaults.
* **Heuristic Fallback Engine**: If Gemini credentials are unconfigured or the remote API experiences timeouts/errors, the system transparently falls back to deterministic rule-based diagnosis.

### 2.4 Recovery Automation & Human-in-the-Loop Approval
* **RBAC Enforcement**: Only users with the `operator` or `admin` role can approve (`/api/v1/recoveries/{id}/approve`) or execute (`/api/v1/recoveries/{id}/execute`) recovery actions. Viewers receive `403 Forbidden`.
* **State Machine**:
  $$\text{pending\_approval} \xrightarrow{\text{approve}} \text{approved} \xrightarrow{\text{execute}} \text{running} \xrightarrow{\text{remediate}} \text{completed} \xrightarrow{\text{verify}} \text{verified / failed}$$
* **Simulated Recovery Adapter**: `SimulatedAgentClient` dispatches signed envelopes (`ActionRequest`) with unique nonces, returning realistic diagnostic receipts without executing arbitrary host shell commands or mounting the Docker socket.
* **Post-Recovery Verification**: `PostRecoveryVerifier` evaluates service telemetry post-remediation. Successful verification resolves the incident; failed verification escalates to human operators.

### 2.5 Multi-Tenant Organization Isolation
* Every request is authenticated via short-lived JWT access tokens containing the user's `org_id`.
* All database queries filter strictly by `organization_id == org.id`.
* Cross-tenant access to incidents, services, recoveries, audit logs, or PDF reports is rejected with `404 Not Found`.

---

## 3. Technology Stack

| Layer | Technologies | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, SWR, Lucide Icons | Responsive operator console, real-time telemetry streaming |
| **Backend** | FastAPI, Python 3.12, Uvicorn, Pydantic v2 | High-performance asynchronous REST API and webhook ingestion |
| **Database** | PostgreSQL 16, SQLAlchemy 2.0 (AsyncIO), Asyncpg, Alembic | ACID relational persistence, migrations, tenant-scoped indexing |
| **Async Tasks** | Celery 5.4, Redis 7, Celery Beat | Background metric aggregation, periodic health sweeps |
| **Monitoring** | Prometheus 2.51, Alertmanager 0.27, Node Exporter, cAdvisor | Telemetry scraping, SLO evaluation, webhook routing |
| **Reporting** | ReportLab 4.1 | Cryptographically signed post-mortem PDF generation |
| **Security** | Argon2id, PyJWT, Cryptography, Secrets | Password hashing, token rotation, HMAC signatures |

---

## 4. Network & Service Topology

```
Host (Windows / Linux)
│
├── 127.0.0.1:3000 -> autoheal_frontend_dev (Next.js)
├── 127.0.0.1:8000 -> autoheal_backend_dev (FastAPI)
├── 127.0.0.1:9090 -> autoheal_prometheus_dev (Prometheus)
├── 127.0.0.1:9093 -> autoheal_alertmanager_dev (Alertmanager)
├── 127.0.0.1:8080 -> autoheal_test_checkout_api
├── 127.0.0.1:8081 -> autoheal_test_customer_web
├── 127.0.0.1:8082 -> autoheal_test_payments_api
│
└── Internal Bridge Network: autoheal_dev_network
    ├── autoheal-api:8000 (FastAPI backend alias)
    ├── db:5432 (PostgreSQL)
    ├── redis:6379 (Redis)
    ├── prometheus:9090
    ├── alertmanager:9093
    ├── celery_worker
    └── celery_beat
```
