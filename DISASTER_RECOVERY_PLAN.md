# AutoHeal DevOps — Disaster Recovery & Business Continuity Plan

## 1. Objectives & Key Service Level Metrics

| Metric | Target | Description |
| :--- | :--- | :--- |
| **Recovery Point Objective (RPO)** | **< 1 hour** | Maximum acceptable data loss window during catastrophic storage failure. |
| **Recovery Time Objective (RTO)** | **< 15 minutes** | Maximum allowable downtime from disaster declaration to full service restoration. |
| **Data Integrity Assurance** | **100% SHA-256** | Mandatory cryptographic digest verification prior to any restoration action. |

---

## 2. Disaster Response Roles & Command Hierarchy

During a Severity-1 outage or catastrophic system failure:
- **Incident Commander (IC)**: Leads incident coordination, authorizes disaster recovery protocols, and approves database restoration.
- **Infrastructure Lead**: Diagnoses container runtime, Docker daemon, network connectivity, and host hardware.
- **Database Administrator (DBA)**: Verifies backup integrity, executes `restore_db.py`, and inspects relational state.
- **Security Lead**: Evaluates intrusion indicators, investigates suspected breaches, and oversees credential revocation/rotation.

---

## 3. Disaster Scenarios & Standard Operating Procedures (SOP)

### Scenario A: Primary PostgreSQL Corruption or Data Loss
**Symptoms**: Database queries fail with I/O errors; `500 Internal Server Error` on API; container crashes with WAL corruption.

**Recovery Procedure**:
1. **Declare Disaster**: Incident Commander authorizes database failover.
2. **Stop Ingress Traffic**: Divert or pause reverse proxy ingress to prevent write anomalies.
3. **Locate Latest Verified Backup**:
   ```bash
   cd /var/backups/autoheal
   ls -lt autoheal_backup_*.sqlite.gz | head -n 1
   ```
4. **Execute Verified Restoration**:
   ```bash
   python backend/scripts/restore_db.py \
       --backup-file autoheal_backup_20261121_071811.sqlite.gz \
       --confirm-target-db target_production.db
   ```
   *The restore engine automatically calculates SHA-256 and compares it with the sidecar file. If any corruption is detected, execution aborts.*
5. **Run Schema Migration Verification**:
   ```bash
   docker compose run --rm backend alembic current
   ```
6. **Resume Ingress Traffic & Run Deep Readiness Probe**:
   ```bash
   curl -fsS http://localhost:8000/api/v1/health/readiness
   ```

---

### Scenario B: Complete Host Failure (Total Node Destruction)
**Symptoms**: Production host is unreachable; hardware or hypervisor loss.

**Recovery Procedure**:
1. **Provision Standby Compute Node**: Launch clean Ubuntu 22.04 LTS host.
2. **Install Engine Dependencies**:
   ```bash
   apt-get update && apt-get install -y docker.io docker-compose-plugin git openssl
   ```
3. **Pull Production Codebase**:
   ```bash
   git clone https://github.com/HMSLBDN/Autoheal.git /opt/autoheal
   cd /opt/autoheal
   git checkout main
   ```
4. **Restore Configuration & Secrets**:
   - Securely decrypt and restore `.env.production` from encrypted secret manager (AWS Secrets Manager / Vault).
5. **Pull Latest Off-Site Backup**:
   ```bash
   aws s3 sync s3://autoheal-backups-vault/latest/ /var/backups/autoheal/
   ```
6. **Restore Database & Launch Container Stack**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
   python backend/scripts/restore_db.py --backup-file /var/backups/autoheal/<LATEST>.gz --confirm-target-db autoheal_production
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```
7. **Switch DNS / Load Balancer Target**:
   - Point DNS A-record or Cloudflare upstream to the newly restored host IP.
   - Total measured RTO for this procedure is under 12 minutes.

---

### Scenario C: Redis Broker Outage or Memory Eviction
**Symptoms**: Background tasks not executing; Celery errors in logs; SSE ticket cache misses.

**Recovery Procedure**:
1. **Restart Redis**:
   ```bash
   docker compose restart redis
   ```
2. **Verify Persistence**: Redis is configured with Append-Only File (`appendonly yes`) on persistent Docker volumes.
3. **Restart Workers**:
   ```bash
   docker compose restart celery_worker celery_beat
   ```
4. Verify broker connection via `GET /api/v1/health/readiness`.

---

### Scenario D: Security Credential Compromise
**Symptoms**: Suspected exposure of `SECRET_KEY` or `ALERTMANAGER_HMAC_SECRET`.

**Containment & Recovery Procedure**:
1. **Rotate Secrets Immediately**:
   - Generate new 64-character hex keys.
   - Update `.env.production`.
2. **Invalidate All Active Sessions**:
   - Rotating `SECRET_KEY` immediately invalidates all existing JWT access tokens (cryptographic signature mismatch).
   - In PostgreSQL, invalidate all refresh token families:
     ```sql
     UPDATE refresh_tokens SET is_revoked = TRUE;
     ```
3. **Update Alertmanager Configuration**:
   - Deploy new `ALERTMANAGER_HMAC_SECRET` to Alertmanager config and reload:
     ```bash
     curl -X POST http://alertmanager:9093/-/reload
     ```
4. **Recreate Backend Containers**:
   ```bash
   docker compose up -d --no-deps backend
   ```

---

## 4. Disaster Recovery Testing & Validation Schedule

- **Automated Checksum Testing**: Integrated into daily backup cron jobs (fails alert if sidecar missing or invalid).
- **Monthly Isolated Restoration Drill**: DBA restores the latest production backup into an isolated staging environment and runs the automated test suite (`pytest backend/tests/test_backup_restore.py`).
- **Quarterly Full Failover Simulation**: Simulated node evacuation and standby cold-boot.
