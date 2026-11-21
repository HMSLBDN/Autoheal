# AutoHeal DevOps — Security & Access Governance Report
**Scope**: Enterprise RBAC, Multi-Tenant Boundary Enforcement, Secret Handling & Platform Hardening  
**Auditor**: Principal Security Architect & DevSecOps Lead  
**Assessment Target**: AutoHeal DevOps SaaS Phase 13 Release Candidate

---

## 1. Executive Summary

This Security and Access Governance Report provides verifiable proof of platform security controls. All access boundaries, cryptographic operations, role hierarchies, and multi-tenant partitioning mechanisms have been validated with automated security regression tests.

---

## 2. Role-Based Access Control (RBAC) Permission Matrix

AutoHeal enforces three primary operational roles:

| Resource / Capability | Viewer | Operator | Administrator | Security Guard Enforced |
|---|:---:|:---:|:---:|---|
| **View Dashboards & Service Health** | :white_check_mark: | :white_check_mark: | :white_check_mark: | Scoped to active `organization_id`. |
| **Inspect Incidents & Correlated Evidence** | :white_check_mark: | :white_check_mark: | :white_check_mark: | Read-only access to timeline and diagnosis. |
| **Acknowledge Incident** | :x: | :white_check_mark: | :white_check_mark: | Rejects Viewers with HTTP 403 (`RequireOperatorDep`). |
| **Request Controlled Recovery** | :x: | :white_check_mark: | :white_check_mark: | Rejects Viewers with HTTP 403. |
| **Approve Policy-Gated Recovery** | :x: | :white_check_mark: | :white_check_mark: | Rejects Viewers with HTTP 403. Tested in Scenario C. |
| **Execute Approved Remediation** | :x: | :white_check_mark: | :white_check_mark: | Enforces signed agent envelope and allowlist. |
| **Transition Incident State** | :x: | :white_check_mark: | :white_check_mark: | Validates lifecycle state machine; rejects Viewers with 403. |
| **Invite Team Members** | :x: | :x: | :white_check_mark: | Rejects Operators & Viewers with HTTP 403 (`RequireAdminDep`). |
| **Manage Notification Channels** | :white_check_mark: (Read) | :white_check_mark: (Test) | :white_check_mark: (Full) | Channel credentials masked with `********`. |
| **Configure Enterprise SSO / IdP** | :x: | :x: | :white_check_mark: | Restricted strictly to tenant administrators. |
| **Issue / Revoke Agent mTLS Certificates** | :x: | :x: | :white_check_mark: | Managed via internal Certificate Authority (RSA 4096 / ECDSA). |

---

## 3. Privilege Escalation Prevention Verification

### 3.1 Self-Registration Boundary
- **Implementation**: In `backend/app/api/routes/auth.py`, the registration endpoint forces role assignment to `operator` or `viewer`:
  ```python
  safe_role = "operator"
  if payload.role and payload.role.lower() in ("viewer", "operator"):
      safe_role = payload.role.lower()
  ```
- **Evidence**: Any self-registration payload specifying `role="admin"` is clamped to `operator`.

### 3.2 Role-Bounded Invitations
- **Implementation**: In `backend/app/api/routes/onboarding.py`, `/onboarding/invite` requires `RequireAdminDep`. Non-admin users are rejected with HTTP 403.
- **Evidence**: Verified in `test_phase13_pilot_readiness.py::test_02_pilot_onboarding_operator_cannot_invite` (Passed).

---

## 4. Multi-Tenant Isolation Verification

Every database entity (`services`, `incidents`, `recoveries`, `audit_logs`, `notification_channels`, `organization_invitations`, `incident_transitions`) carries a mandatory `organization_id` Foreign Key referencing `organizations.id` with `ondelete="CASCADE"`.

All API routes utilize `OrgDep`, which derives tenant context strictly from the cryptographically verified JWT claim:
```python
stmt = select(Incident).where(Incident.id == incident_id, Incident.organization_id == org.id)
```
- **Cross-Tenant Intrusion Test**: Verified in `test_phase13_pilot_readiness.py::test_10_multi_tenant_isolation`. An operator in Organization Alpha querying or attempting to mutate an incident belonging to Organization Beta receives `HTTP 404 Not Found`.

---

## 5. Secret Handling & Cryptographic Standards

1. **Passwords**: Hashed with **Argon2id** (`passlib.context.CryptContext(schemes=["argon2"])`).
2. **Access Tokens**: Short-lived (15 minutes), signed with PyJWT using HMAC-SHA256. Contain tenant and user claims.
3. **Refresh Tokens**: Cryptographically random 256-bit entropy (`secrets.token_urlsafe(32)`), stored as SHA-256 hashes (`token_hash`). Enforces Refresh Token Rotation (RTR) with family revocation on reuse.
4. **Cookie Security**: Set with `HttpOnly=True`, `SameSite=Strict`, `Secure=True` (in production).
5. **Channel Secret Masking**: All outgoing Slack tokens, webhook URLs, SMTP credentials, and API keys are redacted via `mask_channel_config` into `********`.
6. **Zero Direct Docker Socket Exposure**: The FastAPI application container has zero access to `/var/run/docker.sock`. All agent execution occurs via cryptographically signed message envelopes dispatching strictly approved allowlist commands.
