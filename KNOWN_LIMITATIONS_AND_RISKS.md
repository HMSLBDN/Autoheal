# KNOWN LIMITATIONS, OPERATIONAL RISKS & MITIGATION STRATEGY
## AutoHeal DevOps SaaS — Enterprise Pilot Operational Boundaries

**Document Version:** 1.0.0  
**Phase:** 13 (Controlled Enterprise Pilot Readiness)  
**Classification:** Operational Security & Pilot Risk Governance  
**Status:** ACTIVE

---

## 1. Scope & Purpose

This document provides transparent, exhaustive disclosure of the known technical limitations, architectural boundaries, simulated environments, and operational risks present in AutoHeal as of Phase 13.

Engineering teams participating in the controlled pilot must understand these constraints prior to onboarding real production workloads.

---

## 2. Technical Limitations & Current Boundaries

### 2.1 Recovery Execution Environment (`RECOVERY_SIMULATION_MODE=true`)
- **Limitation:** In accordance with Phase 10–13 safety mandates, all autonomous recovery actions operate under hard-locked simulation mode (`RECOVERY_SIMULATION_MODE=true`).
- **Operational Reality:**
  - Container restarts, cache clear commands, and scaling operations simulate execution and verify against simulated or containerized targets without executing arbitrary host-level commands.
  - The Docker socket (`/var/run/docker.sock`) is explicitly **not mounted** into the FastAPI application container to prevent host-escape vulnerabilities.
- **Production Roadmap:** Production execution requires an isolated external agent (e.g. Kubernetes Operator or Nomad task runner) with restricted service accounts.

### 2.2 Telemetry Ingestion Rate Limits
- **Limitation:** In-memory rate limiting and single-node Redis queuing cap ingestion at approximately 2,500 spans/sec and 5,000 metrics/sec per backend replica.
- **Impact:** High-volume services exceeding this burst limit will experience HTTP 429 throttling on OpenTelemetry OTLP collector endpoints.
- **Mitigation:** Scale Redis to a clustered topology or deploy Kafka/RabbitMQ ingress buffering for enterprise enterprise-grade pipelines.

### 2.3 Single-Region PostgreSQL Standalone
- **Limitation:** The pilot deployment utilizes a single PostgreSQL 16 container with local persistent Docker volume (`pgdata_dev`).
- **Impact:** Multi-region automatic failover is not configured at this layer. Disaster recovery relies on logical point-in-time restores (RTO 1.9s, RPO 0s for atomic snapshots).
- **Mitigation:** For multi-region production, migrate to AWS Aurora PostgreSQL, GCP Cloud SQL, or Patroni HA clusters with cross-region read replicas.

### 2.4 External SSO & IdP Staging
- **Limitation:** Okta, Entra ID (Azure AD), and Google Workspace SAML/OIDC integrations are provisioned via standard OAuth2/OIDC code grant interfaces, but live IdP credentials must be supplied by the enterprise tenant.
- **Fallback:** Default pilot instances utilize internal Argon2id-hashed JWT authentication with refresh token family rotation.

---

## 3. Operational Risks & Mitigation Matrix

| Identified Risk | Severity | Potential Impact | Built-in Platform Mitigation | Pilot Team Action Required |
| :--- | :--- | :--- | :--- | :--- |
| **Accidental Destructive Recovery** | HIGH | Erroneous reboot or scaling of stateful production database | Strict Allowlist (`restart_service`, `clear_cache`, etc.). Unlisted actions throw security violations. Simulation mode hard-locked. | Pilot team must assign `ADMIN` role only to authorized SRE leads. |
| **Notification Fatigue / Alert Storms** | MEDIUM | Engineers ignore critical alerts due to spam | 5-minute sliding SHA-256 deduplication window. State change bypass. | Tune alert rule thresholds to match realistic P95 latency profiles. |
| **Premature Incident Closure** | HIGH | Incidents marked resolved while outages persist | Resolution Safety Guard: `POST /transition` to `resolved` rejected (HTTP 409) unless recovery verification passed or explicit reason $\ge$ 8 chars provided. | Train operators to verify post-recovery health metrics before manual sign-off. |
| **Cross-Tenant Telemetry Bleed** | CRITICAL | Enterprise data visible to external tenant | Row-Level Security (RLS) and strict tenant UUID foreign-key scoping in SQLAlchemy queries. | Periodically audit role assignments and API tokens. |
| **Secret Leakage in UI / Logs** | HIGH | Compromise of Slack/Teams incoming webhooks | Dynamic secret masking (`mask_channel_config`) outputs `********` across all read APIs. Redacted logger masks bearer tokens. | Ensure external logging sinks (e.g. Datadog) also enforce secret filtering. |

---

## 4. Disaster Recovery Risk Assessment

| Scenario | Recovery Mechanism | Evaluated Time | Data Loss Risk |
| :--- | :--- | :--- | :--- |
| **Database Container Crash** | Docker daemon restart policy (`unless-stopped`) | < 5 seconds | None (persistent volume attached) |
| **Database Volume Corruption** | Point-in-time restore via `run_disaster_recovery_exercise.py` | 1.90 seconds | Up to latest snapshot interval (6 hours in automated cron) |
| **Backend API Crash** | FastAPI stateless reload / healthcheck auto-restart | < 2 seconds | In-flight HTTP requests only (idempotent retries handled by client) |
| **Redis Cache Eviction** | In-memory key expiration | Instantaneous | Ephemeral session tokens require refresh token exchange |

---

## 5. Security & Isolation Guardrails

1. **RBAC Least Privilege:**
   - `VIEWER`: Read-only access to dashboards, metrics, and incident history. Cannot execute recovery actions or accept team invites.
   - `OPERATOR`: Can transition incident states, acknowledge alerts, and trigger allowlisted recovery actions.
   - `ADMIN`: Can manage team invitations, configure notification secrets, modify SLO thresholds, and access disaster recovery tools.
2. **Audit Immutability:**
   - Every incident transition creates an append-only row in `incident_transitions` recording `previous_state`, `new_state`, `reason`, `triggered_by`, and UTC timestamp.
   - Rows cannot be updated or deleted via API endpoints.
3. **Network Isolation:**
   - Internal microservices communicate strictly over Docker bridge network (`autoheal-network`). No backend database ports are exposed externally in production profiles.
