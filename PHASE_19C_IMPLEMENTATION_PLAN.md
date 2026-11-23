# Phase 19C: Telemetry Configuration Remediation Implementation Plan

**Project:** AutoHeal DevOps
**Date:** 2026-11-23
**Status:** PROPOSED & INSPECTED (Planning & Inspection Only)
**Safety Architecture:** Layered Safety Controls (Simulation Mode Default; Real Recovery Disabled)
**Target Document:** `PHASE_19C_IMPLEMENTATION_PLAN.md`

---

## 1. Executive Summary & Remediation Objectives

Based on the forensic audit conducted in **Phase 19B** (`PHASE_19B_TELEMETRY_AUDIT.md`), the AutoHeal DevOps telemetry, alerting, and monitoring pipelines require targeted configuration remediation prior to live end-to-end integration testing.

This plan details the exact, file-by-file changes required to achieve the four core remediation objectives:
1. **Rule Consolidation:** Load all 11 intended Prometheus alert rules (5 microservice SLO rules + 6 platform enterprise rules) without duplicates or syntax errors.
2. **Deterministic Service Discovery:** Correct the `checkout-api` hostname resolution so Prometheus scrapes the sample microservice reliably.
3. **Host-Port Hardening:** Restrict exposed monitoring and telemetry host ports to `127.0.0.1` (localhost only).
4. **Secure Secret Management:** Replace hardcoded webhook tokens with a securely generated, environment-driven secret outside Git, ensuring Alertmanager and FastAPI receive the exact same secret.

### Layered Safety Governance Controls
- **Simulation Mode Active by Default:** `RECOVERY_SIMULATION_MODE=true` is enforced across default application settings (`backend/app/config.py`), Docker Compose service definitions, and test runner invocations.
- **Real Recovery Disabled:** `RESTRICTED_DOCKER_AGENT_ENABLED=false` is enforced, preventing invocation of the restricted Docker agent.
- **Architectural Isolation:** The host Docker socket is mounted exclusively into `autoheal_socket_proxy` (unprivileged UID 101); the test runner and backend have zero direct Docker socket access.
- **Non-Destructive Operation:** Application code, databases, and containers remain completely untouched during this planning and inspection phase.

---

## 2. Findings Classification: Verified vs. Assumptions

All statements are classified into verified codebase facts vs. operational assumptions:

| Item | Classification | Evidence / Source |
| :--- | :--- | :--- |
| **Alert Rules Disconnect** | **VERIFIED** | `monitoring/prometheus.yml:9-10` references only `alerts.yml`. `monitoring/prometheus/alert_rules.yml` exists on disk with 6 rules but is unmounted and unloaded. |
| **Zero Rule Duplication** | **VERIFIED** | Cross-file analysis confirmed `monitoring/alerts.yml` defines 5 microservice SLO rules (`ServiceDown`, `HighErrorRate`, `HighLatency`, `CPUSaturation`, `MemoryLeakSuspected`). `monitoring/prometheus/alert_rules.yml` defines 6 platform rules (`HighHttp5xxErrorRate`, `HighApiLatencyP99`, `DatabaseConnectionPoolExhaustion`, `AgentMtlsCertificateExpiringSoon`, `SecurityReplayAttackDetected`, `AutonomousRecoveryFailureRateHigh`). Zero rule name or expression overlap. |
| **Service Discovery Mismatch** | **VERIFIED** | `monitoring/prometheus.yml:33-36` targets `checkout-api:8080`. In `docker-compose.yml:275-296`, the service is named `sample_app` (container `autoheal_sample_app`) without network alias `checkout-api`. |
| **Host Port Exposure** | **VERIFIED** | `docker-compose.yml` maps ports `9090:9090` (Prometheus), `9093:9093` (Alertmanager), `9100:9100` (Node Exporter), `8081:8080` (cAdvisor), and `3001:3000` (Grafana) to `0.0.0.0`. In `docker-compose.dev.yml`, these ports are already bound to `127.0.0.1`. |
| **Hardcoded Webhook Secret** | **VERIFIED** | `monitoring/alertmanager.yml:21` hardcodes `bearer_token: "autoheal_dev_alertmanager_webhook_secret_32chars"`. `docker-compose.yml:42` defaults to `autoheal_alertmanager_hmac_secret_key_32chars`, creating a potential auth mismatch. |
| **Alertmanager bearer_token_file Support** | **VERIFIED** | `docker-compose.yml:171` specifies `prom/alertmanager:v0.27.0`. The `bearer_token_file` directive is natively supported in Alertmanager v0.27.0 (and all versions >= v0.1.0) under `http_config`. |
| **Backend Environment Variables** | **VERIFIED** | `backend/app/config.py:202-206` configures `ALERTMANAGER_HMAC_SECRET` with alias `ALERTMANAGER_WEBHOOK_SECRET` via `AliasChoices`. Both env vars map to the same internal setting. |
| **Insecure Secret Rejection** | **VERIFIED** | `backend/app/config.py:261-270` raises a `ValueError` in `production` and `staging` if `ALERTMANAGER_HMAC_SECRET` is empty or matches known dev defaults. |
| **Isolated Test Service Metrics** | **VERIFIED** | `test_environment/test_service/main.py` implements `/health`, `/status`, and chaos endpoints, but contains zero `/metrics` exposition logic. |
| **Alertmanager Network Delivery** | **ASSUMPTION (PENDING VALIDATION)** | Assumes that once network alias `checkout-api` and rule mounting are configured, Prometheus rule evaluations will trigger Alertmanager webhook deliveries across `autoheal_network`. |

---

## 3. Detailed Change Specifications

### Change 1: Prometheus Alert Rule Consolidation and Mounting

#### 1.1 Objective
Ensure Prometheus loads all 11 alerting rules (5 service-level SLO rules + 6 platform-level enterprise rules) without duplicates, syntax errors, or path conflicts.

#### 1.2 Target Files
1. `monitoring/prometheus.yml`
2. `docker-compose.yml`
3. `docker-compose.dev.yml`

#### 1.3 Existing Configuration

**`monitoring/prometheus.yml` (lines 9-10):**
```yaml
rule_files:
  - "alerts.yml"
```

**`docker-compose.yml` (lines 152-155):**
```yaml
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro
      - promdata:/prometheus
```

**`docker-compose.dev.yml` (lines 153-156):**
```yaml
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro
      - promdata_dev:/prometheus
```

#### 1.4 Proposed Configuration

**`monitoring/prometheus.yml`:**
```yaml
rule_files:
  - "alerts.yml"
  - "alert_rules.yml"
```

**`docker-compose.yml`:**
```yaml
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro
      - ./monitoring/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro
      - promdata:/prometheus
```

**`docker-compose.dev.yml`:**
```yaml
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro
      - ./monitoring/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro
      - promdata_dev:/prometheus
```

#### 1.5 Dependencies & Side Effects
- **Rule Name Uniqueness:** Group names (`autoheal_service_slos` vs `autoheal_enterprise_slo_alerts`) and all 11 alert names are mutually exclusive.
- **Metric Availability:** Rules in `alert_rules.yml` evaluate metrics exported by `backend/app/core/logging.py` and `backend/app/core/metrics.py` (`autoheal_http_requests_total`, `autoheal_db_pool_checked_out`, `autoheal_agent_certs_expiring_soon`, `autoheal_recovery_executions_total`).
- **Routing:** All alerts route to `alertmanager:9093`, grouped by `["alertname", "service", "environment"]`.

#### 1.6 Validation Method (Container-Free)
1. Python YAML parser verifying syntax of `prometheus.yml`, `alerts.yml`, and `alert_rules.yml`.
2. Python schema validator asserting all 11 alert rules contain `alert`, `expr`, `for`, `labels`, and `annotations`.
3. Uniqueness assertion confirming zero duplicate alert names across both files.
4. **Prometheus-Specific Rule Validation (`promtool`):**
   - **Host-Side vs. Container-Side Path Distinction:**
     - Inside the container runtime, both files reside at `/etc/prometheus/alerts.yml` and `/etc/prometheus/alert_rules.yml` relative to Prometheus config `/etc/prometheus/prometheus.yml`.
     - On the host filesystem, the files reside at `monitoring/alerts.yml` and `monitoring/prometheus/alert_rules.yml`.
   - **Host Validation Command:** When `promtool` is available locally on the host, validate rule files directly using explicit host-side relative paths without relying on container directory layout:
     ```bash
     promtool check rules monitoring/alerts.yml monitoring/prometheus/alert_rules.yml
     ```
   - If `promtool` is not installed on the host PATH, container-free validation relies on the Python PromQL/YAML structure validator. Do not start Prometheus containers.

#### 1.7 Rollback Procedure
1. Create pre-change backups: `cp monitoring/prometheus.yml monitoring/prometheus.yml.bak`.
2. To roll back, restore the targeted backup: `cp monitoring/prometheus.yml.bak monitoring/prometheus.yml` and revert compose volume entries.
3. All named Docker volumes (`promdata`, `promdata_dev`) are strictly preserved.

---

### Change 2: Checkout API Service Discovery Hostname Correction

#### 2.1 Objective
Ensure Prometheus resolves and scrapes `checkout-api:8080` via internal Docker DNS on `autoheal_network`.

#### 2.2 Target File
`docker-compose.yml`

#### 2.3 Existing Configuration
**`docker-compose.yml` (lines 275-296):**
```yaml
  sample_app:
    build:
      context: ./monitoring/test_services
      dockerfile: Dockerfile
    image: autoheal-test-service:latest
    container_name: autoheal_sample_app
    restart: unless-stopped
    environment:
      - SERVICE_NAME=checkout-api
      - SERVICE_PORT=8080
      - SERVICE_ENV=production
    ports:
      - "8085:8080"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')\""]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 5s
    networks:
      - autoheal_network
```

#### 2.4 Proposed Configuration
**`docker-compose.yml` (lines 294-297):**
```yaml
    networks:
      autoheal_network:
        aliases:
          - checkout-api
```
*(Matches the pattern in `docker-compose.yml:52-54` where `backend` defines alias `autoheal-api`)*

#### 2.5 Dependencies & Side Effects
- **Test Compatibility:** `backend/tests/test_docker_compose.py` asserts required services (`frontend`, `backend`, `celery_worker`, `celery_beat`, `db`, `redis`, `prometheus`, `alertmanager`, `grafana`, `node_exporter`, `cadvisor`). It does not assert a top-level key name for `sample_app`. Adding the network alias preserves the service key `sample_app` while resolving DNS.
- **Side Effects:** Zero breaking changes. `autoheal_sample_app` responds to both `sample_app` and `checkout-api` on `autoheal_network`.

#### 2.6 Validation Method (Container-Free)
1. Python YAML parser verifying `docker-compose.yml` syntax.
2. Assertion script verifying `config["services"]["sample_app"]["networks"]["autoheal_network"]["aliases"] == ["checkout-api"]`.
3. Execute `test_docker_compose_production_structure` assertions statically to confirm no regressions.

#### 2.7 Rollback Procedure
1. Create pre-change backup: `cp docker-compose.yml docker-compose.yml.bak`.
2. To roll back, restore the backup: `cp docker-compose.yml.bak docker-compose.yml`.
3. All Docker network settings and volumes are preserved.

---

### Change 3: Restricting Host-Port Exposure (Localhost Binding)

#### 3.1 Objective
Prevent unauthorized network exposure of internal monitoring metrics and management dashboards by binding published host ports strictly to `127.0.0.1` in `docker-compose.yml`.

#### 3.2 Target File
`docker-compose.yml`

#### 3.3 Existing Configuration
**`docker-compose.yml`:**
- Lines 163-164 (`prometheus`): `ports: ["9090:9090"]`
- Lines 180-181 (`alertmanager`): `ports: ["9093:9093"]`
- Lines 198-199 (`grafana`): `ports: ["3001:3000"]`
- Lines 214-215 (`node_exporter`): `ports: ["9100:9100"]`
- Lines 234-235 (`cadvisor`): `ports: ["8081:8080"]`
- Lines 286-287 (`sample_app`): `ports: ["8085:8080"]`

#### 3.4 Proposed Configuration
**`docker-compose.yml`:**
- `prometheus`: `ports: ["127.0.0.1:9090:9090"]`
- `alertmanager`: `ports: ["127.0.0.1:9093:9093"]`
- `grafana`: `ports: ["127.0.0.1:3001:3000"]`
- `node_exporter`: `ports: ["127.0.0.1:9100:9100"]`
- `cadvisor`: `ports: ["127.0.0.1:8081:8080"]`
- `sample_app`: `ports: ["127.0.0.1:8085:8080"]`

#### 3.5 Dependencies & Side Effects
- **Inter-Container Communication:** Zero impact. Internal services communicate over `autoheal_network` via container hostnames and internal ports (`prometheus:9090`, `alertmanager:9093`, `autoheal-api:8000`). Inter-container traffic does not traverse host port mappings.
- **Local Developer Access:** Operators retain local debugging access via `http://127.0.0.1:9090`, `http://127.0.0.1:9093`, and `http://127.0.0.1:3001`.
- **Security Validation:** Prevents external interfaces (LAN, WAN, public cloud interfaces) from probing metrics or dashboards.

#### 3.6 Validation Method (Container-Free)
1. Python YAML parser inspecting all service port definitions in `docker-compose.yml`.
2. Assertion confirming every monitoring service port string starts with `127.0.0.1:`.

#### 3.7 Rollback Procedure
Restore from `docker-compose.yml.bak`. All Docker named volumes are preserved.

---

### Change 4: Environment-Driven Secret Management & Git Security

#### 4.1 Objective
Eliminate hardcoded development secrets from configuration files, ensure Alertmanager and FastAPI receive the exact same secret, and guarantee that actual secrets remain outside Git without restoring hardcoded defaults on rollback.

#### 4.2 Target Files
1. `.gitignore`
2. `monitoring/secrets/webhook_token.example` (New Safe Template File)
3. `monitoring/alertmanager.yml`
4. `docker-compose.yml`
5. `.env.example`

#### 4.3 Git Security Configuration

**Target File:** `.gitignore`
Add explicit exclusion rules preventing secret files from being staged or committed:
```gitignore
# AutoHeal Secrets & Tokens
monitoring/secrets/*
!monitoring/secrets/*.example
!monitoring/secrets/.gitkeep
```

**New Safe Template File:** `monitoring/secrets/webhook_token.example`
Provides documentation and placeholders with **no real credentials**:
```
# Place a cryptographically random 32+ character hex token in webhook_token
# Example generation command:
# python -c "import secrets; print(secrets.token_hex(32))"
# Ensure the exact same token is set in .env under ALERTMANAGER_HMAC_SECRET
```

#### 4.4 Secret Generation & Synchronization Procedure
1. **Secure Secret Generation:**
   Generate a fresh, cryptographically strong 64-character hex secret outside Git:
   ```powershell
   $Secret = python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. **Alertmanager Token File:**
   Write the secret directly to `monitoring/secrets/webhook_token` (gitignored, mode 0600 on Linux / restricted ACLs on Windows):
   ```powershell
   Set-Content -Path "monitoring/secrets/webhook_token" -Value $Secret -NoNewline
   ```
3. **Backend Environment Variable:**
   Set the exact same secret into `.env`:
   ```dotenv
   ALERTMANAGER_HMAC_SECRET=<generated_secret>
   ```
4. **Secret Masking:**
   The secret value is never printed to terminal logs, test summaries, or markdown reports.

#### 4.5 Configuration Updates

**`monitoring/alertmanager.yml` (lines 17-22):**
Replace inline token with file-based secret loading:
```yaml
receivers:
  - name: "autoheal-webhook"
    webhook_configs:
      - url: "http://autoheal-api:8000/api/v1/alerts/webhook"
        send_resolved: true
        http_config:
          bearer_token_file: /etc/alertmanager/secrets/webhook_token
        max_alerts: 10
```

**`docker-compose.yml` (backend service, line 42):**
Standardize on `ALERTMANAGER_HMAC_SECRET`:
```yaml
      - ALERTMANAGER_HMAC_SECRET=${ALERTMANAGER_HMAC_SECRET:-}
      - ALERTMANAGER_WEBHOOK_SECRET=${ALERTMANAGER_HMAC_SECRET:-}
```

**`docker-compose.yml` (alertmanager service, lines 174-177):**
Mount the secret file read-only into Alertmanager:
```yaml
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - ./monitoring/secrets/webhook_token:/etc/alertmanager/secrets/webhook_token:ro
      - alertdata:/alertmanager
```

**`.env.example` (lines 53-55):**
```dotenv
# Monitoring & Alerting
PROMETHEUS_URL=http://localhost:9090
ALERTMANAGER_HMAC_SECRET=generate_strong_random_secret_with_python_secrets_token_hex_32
METRIC_SCRAPE_INTERVAL_SECONDS=15
```

#### 4.6 Verification of Component Secret Compatibility
- **Alertmanager v0.27.0 Compatibility:** `bearer_token_file` is fully supported by Prometheus Alertmanager v0.27.0 under `http_config`. It reads the token from the specified file on container startup and during HTTP reload.
- **Backend Compatibility:** `backend/app/config.py:202-206` maps both `ALERTMANAGER_HMAC_SECRET` and `ALERTMANAGER_WEBHOOK_SECRET` to `settings.ALERTMANAGER_HMAC_SECRET`.
- **Backend Ingestion Guard:** `backend/app/api/deps.py:182-185` parses `Authorization: Bearer <token>` from incoming Alertmanager requests and performs constant-time comparison via `hmac.compare_digest(token, settings.ALERTMANAGER_HMAC_SECRET)`.
- **Insecure Default Protection:** `backend/app/config.py:261-270` continues to reject empty, short, or development default secrets in `production` and `staging` environments.

#### 4.7 Validation Method (Container-Free)
1. Verify `monitoring/secrets/webhook_token` is ignored by Git:
   ```powershell
   git check-ignore monitoring/secrets/webhook_token
   ```
2. Verify `git status --porcelain` shows no untracked secret files.
3. Verify `monitoring/secrets/webhook_token.example` contains zero credentials.
4. Python script asserting that `monitoring/secrets/webhook_token` and `.env` `ALERTMANAGER_HMAC_SECRET` contain identical non-empty strings without printing them.

#### 4.8 Rollback Procedure (Secret Safety & Volume Preservation)
1. **Never restore a hardcoded development secret:**
   Do NOT revert `monitoring/alertmanager.yml` to insecure strings (`"autoheal_dev_alertmanager_webhook_secret_32chars"`).
2. **Preserve the generated secret outside Git:**
   Keep `monitoring/secrets/webhook_token` and `.env` intact. The generated secret remains the persistent local authorization token outside Git.
3. **Restore Targeted Configuration Backups:**
   Restore `monitoring/alertmanager.yml` from `monitoring/alertmanager.yml.bak` if required.
4. **Preserve Named Volumes:**
   Alertmanager and Prometheus named volumes (`alertdata`, `promdata`) are never dropped or deleted during rollback.

---

## 4. Downtime Realities, Lifecycle Management & Volume Preservation

### 4.1 Downtime Realities
- **No Zero-Downtime Guarantee:** Applying changes to `docker-compose.yml` (such as adding network aliases, altering volume mounts, or changing port bindings) requires recreating the affected containers (`docker compose up -d`). During container recreation, a brief interruption of service (typically 2–5 seconds) is expected for each restarted container.
- **HTTP Configuration Reloads:** Where containers are already running and volume mounts are already present, Prometheus supports graceful reload via `POST /-/reload` (enabled via `--web.enable-lifecycle` in `docker-compose.yml:161`). Alertmanager supports reload via `POST /-/reload`. However, changes to `docker-compose.yml` itself cannot be applied via HTTP reload and require container recreation.

### 4.2 Data Volume Preservation During Rollback
If changes need to be rolled back or containers recreated:
- **Prometheus TSDB Volume (`promdata` / `promdata_dev`):** Retains all historical metric series. Recreating or restarting the container does not touch the named volume.
- **Alertmanager State Volume (`alertdata` / `alertdata_dev`):** Retains active silences and notification state.
- **Targeted Backup Restoration:** Rollback utilizes targeted `.bak` files (`docker-compose.yml.bak`, `monitoring/prometheus.yml.bak`, `monitoring/alertmanager.yml.bak`).
- **Mandatory Rollback Command Rule:**
  ```powershell
  # CORRECT: Stops containers without touching volumes
  docker compose stop prometheus alertmanager sample_app
  docker compose up -d prometheus alertmanager sample_app

  # FORBIDDEN: Never execute down with -v
  # docker compose down -v  <-- STRICTLY PROHIBITED (destroys data volumes)
  ```

---

## 5. Comprehensive Container-Free Validation Strategy

All changes must be validated statically without starting containers, without executing live tests, and without modifying runtime databases.

### Static Validation Plan

1. **YAML Syntax & Integrity:**
   Execute Python script parsing all configuration files:
   - `monitoring/prometheus.yml`
   - `monitoring/alerts.yml`
   - `monitoring/prometheus/alert_rules.yml`
   - `monitoring/alertmanager.yml`
   - `docker-compose.yml`
   - `docker-compose.dev.yml`

2. **Prometheus-Specific Rule Validation:**
   - Validate that both `alerts.yml` and `alert_rules.yml` are referenced under `rule_files:` in `prometheus.yml`.
   - Validate that all 11 alert rules parse successfully:
     - 5 service SLO rules: `ServiceDown`, `HighErrorRate`, `HighLatency`, `CPUSaturation`, `MemoryLeakSuspected`.
     - 6 platform SLO rules: `HighHttp5xxErrorRate`, `HighApiLatencyP99`, `DatabaseConnectionPoolExhaustion`, `AgentMtlsCertificateExpiringSoon`, `SecurityReplayAttackDetected`, `AutonomousRecoveryFailureRateHigh`.
   - Confirm zero duplicate alert names across both rule files.
   - **Host-Side Promtool Execution:**
     If `promtool` is available locally, run rule checks using explicit host-side relative paths:
     ```bash
     promtool check rules monitoring/alerts.yml monitoring/prometheus/alert_rules.yml
     ```
     *(Note: `promtool check config monitoring/prometheus.yml` resolves `rule_files:` relative to `monitoring/`; because `alert_rules.yml` resides in `monitoring/prometheus/` on the host, host-side config checks should evaluate rules via `promtool check rules` directly to prevent host-vs-container path confusion).*

3. **Service Discovery & Network Alias Validation:**
   - Confirm `docker-compose.yml` defines alias `checkout-api` under `sample_app.networks.autoheal_network.aliases`.
   - Confirm `backend` preserves alias `autoheal-api` under `backend.networks.autoheal_network.aliases`.

4. **Port Binding Hardening Validation:**
   - Confirm all published ports for `prometheus`, `alertmanager`, `node_exporter`, `cadvisor`, `grafana`, and `sample_app` in `docker-compose.yml` are prefixed with `127.0.0.1:`.

5. **Secret Synchronization & Git Exclusion Validation:**
   - Confirm `.gitignore` excludes `monitoring/secrets/*` while keeping `monitoring/secrets/*.example`.
   - Confirm `git status --porcelain` does not show any untracked secret files.
   - Confirm `monitoring/alertmanager.yml` references `bearer_token_file: /etc/alertmanager/secrets/webhook_token`.
   - Confirm `monitoring/secrets/webhook_token` and `.env` `ALERTMANAGER_HMAC_SECRET` match identically without logging the secret.

6. **Python Compilation Check:**
   - Compile backend modules to ensure no syntax regressions:
     ```powershell
     python -m py_compile backend/app/config.py backend/app/api/deps.py backend/app/api/routes/alerts.py
     ```

---

## 6. Risk Matrix & Rollback Procedures

| Risk ID | Risk Description | Severity | Mitigation Strategy | Rollback Procedure |
| :--- | :--- | :--- | :--- | :--- |
| **RSK-19C-01** | Missing volume mount causes Prometheus container boot failure | High | Mount `alert_rules.yml` in both `docker-compose.yml` and `docker-compose.dev.yml` simultaneously. | Restore `prometheus.yml` from `prometheus.yml.bak`. Data volumes preserved. |
| **RSK-19C-02** | Alertmanager secret file missing on disk | Medium | Ensure `monitoring/secrets/webhook_token` is generated before mounting into container. | Restore from `alertmanager.yml.bak`. Preserve generated secret outside Git. Data volumes preserved. |
| **RSK-19C-03** | Secret file accidentally tracked in Git | High | Update `.gitignore` before creating secret file. Verify with `git status --porcelain`. | Untrack file via `git rm --cached` immediately if ever added. |
| **RSK-19C-04** | Compose alias syntax regression | Low | Mirror exact syntax used by `backend.networks.autoheal_network.aliases`. | Restore `docker-compose.yml` from `docker-compose.yml.bak`. |
| **RSK-19C-05** | Service disruption during container recreate | Low | Plan recreation during controlled maintenance window; never pass `-v` flag. | Re-run compose with restored `.bak` file. Volumes preserved. |

---

## 7. Step-by-Step Implementation Sequence (For Phase 19C Execution)

When authorized to implement, execute in the following exact sequence:

1. [ ] **Step 1: Create Targeted Pre-Change Backups**
   - Create `.bak` files:
     - `cp monitoring/prometheus.yml monitoring/prometheus.yml.bak`
     - `cp monitoring/alertmanager.yml monitoring/alertmanager.yml.bak`
     - `docker-compose.yml` $\to$ `docker-compose.yml.bak`
     - `docker-compose.dev.yml` $\to$ `docker-compose.dev.yml.bak`
     - `.gitignore` $\to$ `.gitignore.bak`
2. [ ] **Step 2: Update `.gitignore`**
   - Add `monitoring/secrets/*`, `!monitoring/secrets/*.example`, `!monitoring/secrets/.gitkeep`.
3. [ ] **Step 3: Create Safe Secret Template**
   - Create `monitoring/secrets/webhook_token.example` with instructions and no real credentials.
4. [ ] **Step 4: Securely Generate and Sync Real Webhook Secret**
   - Generate fresh random 64-character hex secret via Python `secrets.token_hex(32)`.
   - Write to `monitoring/secrets/webhook_token` (gitignored).
   - Set in `.env` as `ALERTMANAGER_HMAC_SECRET`.
   - Do not print or log the secret value.
5. [ ] **Step 5: Update `monitoring/alertmanager.yml`**
   - Replace inline `bearer_token` with `bearer_token_file: /etc/alertmanager/secrets/webhook_token`.
6. [ ] **Step 6: Update `monitoring/prometheus.yml`**
   - Add `- "alert_rules.yml"` to `rule_files:`.
7. [ ] **Step 7: Update `docker-compose.yml`**
   - Mount `./monitoring/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro`.
   - Mount `./monitoring/secrets/webhook_token:/etc/alertmanager/secrets/webhook_token:ro`.
   - Add `aliases: - checkout-api` to `sample_app` under `autoheal_network`.
   - Bind published ports for `prometheus`, `alertmanager`, `grafana`, `node_exporter`, `cadvisor`, and `sample_app` to `127.0.0.1`.
   - Standardize `backend` environment variables to `ALERTMANAGER_HMAC_SECRET`.
8. [ ] **Step 8: Update `docker-compose.dev.yml`**
   - Mount `./monitoring/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro`.
9. [ ] **Step 9: Execute Container-Free Validation Suite**
   - Validate YAML syntax of all modified files.
   - Validate all 11 alert rules and confirm zero duplicate alert names.
   - Run `promtool check rules` on `monitoring/alerts.yml` and `monitoring/prometheus/alert_rules.yml` if locally available.
   - Confirm Git ignores `monitoring/secrets/webhook_token` and tracks no secrets (`git status --porcelain`).
   - Compile backend modules via `python -m py_compile`.
10. [ ] **Step 10: Stop and Present Results**
    - Show exact diffs of all modified files and wait for user approval before container restart or live testing.
