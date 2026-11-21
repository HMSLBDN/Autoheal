# CONTROLLED PILOT READINESS CHECKLIST & OPERATIONAL RUNBOOK

**Project:** AutoHeal DevOps SaaS  
**Milestone:** Phase 11 Controlled Pilot  
**Default Security Setting:** `RECOVERY_SIMULATION_MODE=true`  
**Target Environment:** Staging / Controlled Pilot Cluster  
**Status:** READY FOR OPERATIONAL PILOT

---

## 1. Pilot Rollout Stages

To ensure zero risk of unintended downtime or misconfiguration, the rollout must proceed through four distinct operational stages:

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Shadow Telemetry & Ingestion Pilot (Current State) │
│ - Ingest real metrics, traces, and alerts                   │
│ - Zero automated actions executed                           │
│ - RECOVERY_SIMULATION_MODE=true locked                      │
└──────────────────────────────┬──────────────────────────────┘
                               │ (7 Consecutive Days Zero Error)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Assisted SRE Recommendation Pilot                  │
│ - AI & Rule Engine generate diagnostic recommendations      │
│ - Operator approval REQUIRED for every remediation action   │
│ - Actions executed in simulation mode only                  │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Sign-off from SRE Lead)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Controlled Canary Automated Remediation            │
│ - Low-risk actions auto-approved on non-critical dev/canary │
│ - (e.g. log vacuuming, cache eviction, canary restart)      │
│ - High-risk actions require dual human authorization        │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Executive & Security Approval)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: Production High-Availability Pilot                 │
│ - Multi-AZ failover and auto-scaling automated              │
│ - Instant automated rollback upon canary failure            │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Operational Readiness Checklist

### A. Environment & Infrastructure Guardrails
- [x] `RECOVERY_SIMULATION_MODE=true` hard-coded and validated in environment config.
- [x] Zero external deployment scripts active in CI/CD pipeline.
- [x] Database credentials managed strictly through KMS / encrypted environment variables.
- [x] mTLS certificate authority initialized with minimum 2048-bit RSA keys.
- [x] Webhook SSRF protection actively filtering private IPv4 and IPv6 subnets.

### B. Authentication & Access Governance
- [x] Default administrative password rotated and Argon2id enforced.
- [x] OIDC identity provider configured with PKCE S256 code challenge.
- [x] Session idle timeout configured to 15 minutes.
- [x] Maximum concurrent sessions per user capped at 3.
- [x] Anti-cross-tenant token validation enabled and verified.

### C. Observability & Incident Safety
- [x] OpenTelemetry trace exporter initialized with W3C context propagation.
- [x] Sensitive credential redaction verified across all exported spans.
- [x] Circuit breaker threshold configured on external AI API integrations.
- [x] Deterministic heuristic fallback rules tested and operational.
- [x] Dead-Letter Queue (DLQ) configured for undeliverable webhook notifications.

---

## 3. Emergency Kill-Switches & Rollback Procedures

If anomalous behavior, runaway scaling, or unexpected remediation loops occur:

### 1. Global Simulation Emergency Override
Execute via administrative CLI or FastAPI environment configuration:
```bash
export RECOVERY_SIMULATION_MODE=true
export AUTONOMOUS_HEALING_ENABLED=false
```
*Effect:* Instantly halts all active recovery actions, freezes automated executions, and forces all pending recommendations into the operator review queue.

### 2. Immediate Session Revocation
To terminate all active operator sessions in the event of suspected credential compromise:
```sql
UPDATE sessions SET is_revoked = true WHERE is_revoked = false;
```

### 3. Agent mTLS Revocation
To revoke an individual compromised edge node:
```bash
python -m app.services.infrastructure.mtls_ca revoke-agent --serial <SERIAL_NUMBER>
```
*Effect:* Node agent connection is immediately terminated during TLS handshake.
