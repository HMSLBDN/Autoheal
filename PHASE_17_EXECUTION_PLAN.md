# Phase 17: Controlled Integration Testing — Execution Plan

**Project:** AutoHeal DevOps  
**Repository:** `https://github.com/HMSLBDN/Autoheal.git`  
**Branch:** `main` | **Target Stage:** Phase 17 Controlled Integration Testing  
**Status:** **APPROVED EXECUTION PLAN**

---

## 1. Architectural & Safety Foundations

### A. Location of the Backend Integration Test Harness
Because `docker-compose.test-infra.yml` attaches services to an air-gapped network (`autoheal_test_network`, `internal: true`) with **zero published host ports**, processes on the host machine cannot resolve `autoheal_test_service:8080` or `autoheal_docker_agent:8091`.

* **Where the Harness Runs:** The backend integration test harness executes inside an **ephemeral runner container** attached directly to `autoheal_test_network`:
  ```powershell
  docker run --rm `
    --network autoheal_test_network `
    -v "${PWD}:/app:ro" `
    -w /app `
    -e PYTHONPATH="backend:." `
    -e RECOVERY_SIMULATION_MODE=true `
    -e RESTRICTED_DOCKER_AGENT_ENABLED=false `
    -e DOCKER_AGENT_SECRET_KEY=$env:DOCKER_AGENT_SECRET_KEY `
    python:3.11-slim python scratch/run_phase17_harness.py
  ```
* **Why This Is Secure & Functional:**
  1. The container leverages Docker's embedded DNS (`127.0.0.11`) to resolve `autoheal_test_service:8080` and `autoheal_docker_agent:8091` natively.
  2. The workspace is mounted as **read-only** (`:ro`), preventing any code or configuration alteration.
  3. No ports are published to the host (`127.0.0.1` or `0.0.0.0`).
  4. The ephemeral container automatically self-destructs upon completion (`--rm`).

### B. Git Baseline Preservation & Invariance Tracking
* **Existing Phase 16 State:** The repository contains approved, committed Phase 16 scaffolding and security hardening files.
* **Preservation Guarantee:** No `git checkout`, `git restore`, `git reset`, `git clean`, `git add`, `git commit`, or `git push` commands will be executed during test runs without user instruction.
* **Preflight Snapshot:** At preflight, record the baseline working tree state:
  ```powershell
  git status --porcelain > scratch/phase17_baseline_git_status.txt
  ```
* **Post-Test Verification:** Compare `git status --porcelain` against the baseline snapshot. Phase 17 must introduce **zero additional modifications or untracked files**.

### C. Accurate Simulation Safety Architecture (No False Immutability Claims)
* **Configuration Reality:** In `backend/app/config.py`, `RECOVERY_SIMULATION_MODE: bool = Field(default=True)` is managed by Pydantic `BaseSettings`. An operator setting the OS environment variable `RECOVERY_SIMULATION_MODE=false` will cause Pydantic to parse it as `False`. It is **not** an immutable constant.
* **Multi-Gate Defense-in-Depth:**
  1. **Secondary Control Plane Gate:** In `backend/app/services/recovery/executor.py` (lines 48, 114, 133), real execution requires **both** `not settings.RECOVERY_SIMULATION_MODE` **and** `getattr(settings, "RESTRICTED_DOCKER_AGENT_ENABLED", False)`. Because `RESTRICTED_DOCKER_AGENT_ENABLED` defaults to `False`, setting `RECOVERY_SIMULATION_MODE=false` alone continues to instantiate `SimulatedAgentClient`.
  2. **Agent-Level Gate:** In `docker_agent/server.py` (lines 200–220), `settings.SIMULATION_MODE` actively intercepts restart requests, raising HTTP `403 Forbidden` (`"Restart operations are blocked in simulation mode."`).
  3. **Compose Service Gate:** In `docker-compose.test-infra.yml` (line 74), `RECOVERY_SIMULATION_MODE=true` is set for the container process.
  4. **Docker Client Core Gate:** In `docker_agent/docker_client.py` (line 225), `DockerEngineClient.restart_container()` intercepts execution if `settings.SIMULATION_MODE` is `True`, generating a simulated receipt (`is_mocked: True`).

---

## 2. Preflight Checks & Rollback Plan

### Preflight Checklist
1. **Docker Engine:** Run `docker info` to verify daemon connectivity.
2. **Git Baseline Snapshot:** Save initial `git status --porcelain` to `scratch/phase17_baseline_git_status.txt`.
3. **Certificate Integrity:** Verify that `docker_proxy/certs/` contains `ca.crt`, `proxy.crt`, `agent.crt`, and `agent.key`, and that `proxy.crt` contains SAN `DNS:autoheal_socket_proxy`.
4. **Core Stack Exclusion:** Run `docker ps` to verify 0 core AutoHeal containers are running.
5. **Fresh Secret Generation:** Generate an ephemeral 256-bit cryptographically secure pseudorandom secret:
   ```powershell
   $env:DOCKER_AGENT_SECRET_KEY = (.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))")
   ```

### Rollback Plan
If any step fails, hangs, or encounters unexpected output:
```powershell
# 1. Stop and remove isolated test containers (strictly without -v to preserve all volumes)
docker compose -f docker-compose.test-infra.yml down

# 2. Clear ephemeral agent secret from process environment
Remove-Item Env:\DOCKER_AGENT_SECRET_KEY -ErrorAction SilentlyContinue

# 3. Confirm zero leftover containers
docker ps -a

# 4. Verify working tree matches preflight snapshot
git status --porcelain
```

---

## 3. Step-by-Step Execution Plan

```
+----------------------------------------------------------------------------------------------------+
|                                    PHASE 17 EXECUTION STAGES                                       |
|                                                                                                    |
|  [ Stage 1: Test Infra Startup ] ---->  docker compose up -d (Internal network, zero host ports)   |
|                                                                                                    |
|  [ Stage 2: mTLS & Route Audit ] ---->  docker compose exec agent -> NGINX mTLS verification       |
|                                                                                                    |
|  [ Stage 3: Agent Comm ] ------------>  docker compose exec agent -> Health & allowlist inspection |
|                                                                                                    |
|  [ Stage 4: Chaos Degradation ] ----->  docker compose exec test_service -> POST /chaos/degrade    |
|                                                                                                    |
|  [ Stage 5-8: Ephemeral Harness ] --->  docker run --rm --network autoheal_test_network ...        |
|                                         - Resolves autoheal_test_service:8080                      |
|                                         - In-memory SQLite session (zero DB volume mounts)         |
|                                         - Ingests alert & generates simulated recovery             |
|                                         - Probes 503 degraded service -> VERIFICATION_FAILED       |
|                                         - Confirms incident remains "investigating"                |
|                                                                                                    |
|  [ Stage 9: Positive Branch Test ] -->  Reset chaos -> Independent verifier run -> HEALTH_VERIFIED |
|                                                                                                    |
|  [ Stage 10: Safe Teardown ] -------->  docker compose down (no -v), compare git status, report    |
+----------------------------------------------------------------------------------------------------+
```

---

### Step 1: Isolated Infrastructure Startup
* **Action:** Start solely `autoheal_socket_proxy`, `autoheal_test_service`, and `autoheal_docker_agent`.
* **Command:**
  ```powershell
  docker compose -f docker-compose.test-infra.yml up -d
  ```
* **Verification:**
  * Run `docker compose -f docker-compose.test-infra.yml ps`.
  * Confirm all 3 containers report state `Up`.
  * Confirm `PORTS` column displays internal container ports only (`8080/tcp`, `8091/tcp`, `8443/tcp`). Zero ports published to `0.0.0.0` or `127.0.0.1`.

---

### Step 2: NGINX Proxy & mTLS Connectivity Audit
* **Action:** Validate internal mTLS handshake and exact identity matching from within `autoheal_docker_agent`.
* **Command:**
  ```powershell
  docker compose -f docker-compose.test-infra.yml exec autoheal_docker_agent python -c "
  import urllib.request, ssl, json
  ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile='/etc/ssl/certs/autoheal/ca.crt')
  ctx.load_cert_chain('/etc/ssl/certs/autoheal/agent.crt', '/etc/ssl/certs/autoheal/agent.key')
  req = urllib.request.Request('https://autoheal_socket_proxy:8443/containers/autoheal_test_service/json')
  with urllib.request.urlopen(req, context=ctx) as resp:
      print('Proxy mTLS Handshake Status:', resp.status)
  "
  ```
* **Acceptance Criteria:**
  * Returns HTTP `200 OK`.
  * Handshake fails if client certificate is omitted.
  * Target container query to unapproved routes (e.g. `POST /containers/create`) returns HTTP `403 Forbidden`.

---

### Step 3: Docker Agent Internal Communication & Allowlist Check
* **Action:** Query the agent API internally over `localhost:8091` inside `autoheal_docker_agent`.
* **Commands:**
  ```powershell
  # A. Check Agent Health
  docker compose -f docker-compose.test-infra.yml exec autoheal_docker_agent python -c "
  import urllib.request, json
  resp = urllib.request.urlopen('http://localhost:8091/health')
  print('Agent Health:', resp.status, json.loads(resp.read().decode())['simulation_mode'])
  "

  # B. Check Approved Container Inspection
  docker compose -f docker-compose.test-infra.yml exec autoheal_docker_agent python -c "
  import urllib.request, json
  resp = urllib.request.urlopen('http://localhost:8091/api/v1/containers/autoheal_test_service')
  print('Inspect Approved Status:', resp.status)
  "

  # C. Check Unapproved Container Rejection
  docker compose -f docker-compose.test-infra.yml exec autoheal_docker_agent python -c "
  import urllib.request, urllib.error
  try:
      urllib.request.urlopen('http://localhost:8091/api/v1/containers/autoheal_postgres')
  except urllib.error.HTTPError as e:
      print('Unapproved Container HTTP Code:', e.code)
  "
  ```
* **Acceptance Criteria:**
  * Health reports HTTP `200 OK`, `simulation_mode: true`.
  * Inspection of `autoheal_test_service` returns HTTP `200 OK`.
  * Inspection of `autoheal_postgres` raises HTTP `403 Forbidden`.

---

### Step 4: Dedicated Test-Service Chaos Injection
* **Action:** Induce simulated failure directly within `autoheal_test_service`.
* **Commands:**
  ```powershell
  # A. Confirm Baseline Healthy State
  docker compose -f docker-compose.test-infra.yml exec autoheal_test_service python -c "
  import urllib.request, json
  resp = urllib.request.urlopen('http://localhost:8080/health')
  print('Baseline Health:', resp.status)
  "

  # B. Inject Chaos Degradation
  docker compose -f docker-compose.test-infra.yml exec autoheal_test_service python -c "
  import urllib.request, json
  req = urllib.request.Request(
      'http://localhost:8080/chaos/degrade',
      data=json.dumps({'failure_type': 'thread_exhaustion'}).encode(),
      headers={'Content-Type': 'application/json'}
  )
  resp = urllib.request.urlopen(req)
  print('Chaos Injected:', resp.status)
  "

  # C. Confirm Service Reports 503 Unhealthy
  docker compose -f docker-compose.test-infra.yml exec autoheal_test_service python -c "
  import urllib.request, urllib.error
  try:
      urllib.request.urlopen('http://localhost:8080/health')
  except urllib.error.HTTPError as e:
      print('Degraded Health Status:', e.code)
  "
  ```
* **Acceptance Criteria:**
  * Baseline returns HTTP `200 OK`.
  * Degradation returns HTTP `200 OK`.
  * Subsequent `/health` probe returns HTTP `503 Service Unavailable`.

---

### Step 5–8: Ephemeral Backend Integration Harness (Stages 5 through 8)
* **Where It Runs:** An ephemeral runner container attached to `autoheal_test_network`, mounting the workspace read-only (`:ro`).
* **Command:**
  ```powershell
  docker run --rm `
    --network autoheal_test_network `
    -v "${PWD}:/app:ro" `
    -w /app `
    -e PYTHONPATH="backend:." `
    -e RECOVERY_SIMULATION_MODE=true `
    -e RESTRICTED_DOCKER_AGENT_ENABLED=false `
    -e DOCKER_AGENT_SECRET_KEY=$env:DOCKER_AGENT_SECRET_KEY `
    python:3.11-slim python scratch/run_phase17_harness.py
  ```
* **Harness Workflow Inside Container:**
  1. **Stage 5 (Alert Ingestion):** Uses an in-memory SQLite database (`sqlite+aiosqlite:///:memory:`). Ingests mock Prometheus alert for `autoheal_test_service`. Creates incident `INC-PHASE17-001` in status `"open"`.
  2. **Stage 6 (AI Diagnosis & Policy Gate):** RCA recommends `restart_container`. Policy Engine confirms `autoheal_test_service` is allowlisted. Incident transitions to `"investigating"`. Recovery action approved.
  3. **Stage 7 (Simulated Recovery Execution):** `RecoveryExecutor` executes recovery. Simulation mode intercepts the call. Generates receipt with `execution_mode: "SIMULATED"`, `evidence_classification: "SIMULATED"`, `is_mocked: True`. Real Docker restart is **not** called.
  4. **Stage 8 (Honest Health Verification):** `PostRecoveryVerifier` probes `http://autoheal_test_service:8080/health`. Because recovery was simulated, the service is **still degraded** (HTTP `503`).
     * Verifier marks `recovery.verification = "failed"`.
     * Verifier sets `recovery.evidence_classification = "VERIFICATION_FAILED"`.
     * Incident status remains `"investigating"` (is **not** resolved; `resolved_at` is `None`).
     * Escalation event and audit log recorded in database session.
* **Acceptance Criteria:**
  * The harness completes cleanly, demonstrating that AutoHeal refuses to mark incidents resolved when simulated actions do not repair degraded services.

---

### Step 9: Positive Verification Branch (Baseline Chaos Reset Test)
* **Action:** Validate that `PostRecoveryVerifier` successfully recognizes a healthy service when degradation is cleared.
* **Execution:**
  1. Reset chaos state in `autoheal_test_service`:
     ```powershell
     docker compose -f docker-compose.test-infra.yml exec autoheal_test_service python -c "
     import urllib.request
     req = urllib.request.Request('http://localhost:8080/chaos/reset', data=b'{}', headers={'Content-Type':'application/json'})
     urllib.request.urlopen(req)
     "
     ```
  2. Run secondary isolated verifier harness probing `http://autoheal_test_service:8080/health`:
     * Service returns HTTP `200 OK`.
     * Verifier marks `recovery.verification = "passed"`.
     * Verifier sets `recovery.evidence_classification = "HEALTH_VERIFIED"`.
     * Incident status transitions to `"resolved"`, `resolved_at` recorded.

---

### Step 10: Safe Teardown & Post-Test Verification
* **Action:** Gracefully shut down test infrastructure preserving all Docker volumes, and verify working tree.
* **Commands:**
  ```powershell
  # 1. Stop and remove test containers safely (no -v)
  docker compose -f docker-compose.test-infra.yml down

  # 2. Clear ephemeral agent secret
  Remove-Item Env:\DOCKER_AGENT_SECRET_KEY -ErrorAction SilentlyContinue

  # 3. Verify zero leftover containers
  docker ps -a

  # 4. Verify working tree matches preflight snapshot
  git status --porcelain
  ```
* **Acceptance Criteria:**
  * 0 test containers running or stopped.
  * `autoheal_test_network` removed.
  * Production Docker volume `postgres_data` intact.
  * Git working tree status identical to `scratch/phase17_baseline_git_status.txt` (zero unintended modifications).

---

## 4. Summary of Strict Safety Invariants

| Safety Rule | Verification & Enforcement |
| :--- | :--- |
| **`RECOVERY_SIMULATION_MODE=true`** | Enforced in code and Compose environment. Real restart commands raise HTTP 403. |
| **Zero Real Docker Restarts** | Tested against degraded container; service remains degraded, proving no real restart occurred. |
| **Database Data Isolation** | Test execution interacts exclusively with in-memory SQLite sessions. Production PostgreSQL volume is never mounted. |
| **Zero Published Host Ports** | Test services expose ports strictly to `autoheal_test_network` (internal). Accessed solely via `docker compose exec`. |
| **Safe Volume Preservation** | Cleanup uses `docker compose down` (no `-v`). Existing Docker volumes are untouched. |
| **Git Immutability** | Zero staging, committing, pushing, or deploying during Phase 17 execution. |
