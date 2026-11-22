# AutoHeal DevOps — Security Architecture & Recovery Safety

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1)  
**Applicability:** Security Architects, Compliance Officers, Infrastructure Engineers  
**Core Principle:** Defense-in-depth with mandatory non-destructive execution boundaries.

---

## 1. Security Architecture Overview

AutoHeal DevOps incorporates zero-trust principles across its entire operational envelope. The platform is designed to assist engineers with incident diagnosis and recovery orchestration while strictly preventing unauthorized access, arbitrary command execution, or uncontrolled infrastructure modification.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Zero-Trust Security Perimeter                   │
│                                                                        │
│  [ External Ingress ]                                                  │
│        │                                                               │
│        ├─► TLS Termination & Forwarded IP Filtering                    │
│        ├─► Token-Bucket Rate Limiter (IP & Account scoped)             │
│        └─► CORS Whitelist (Strict origin checking)                     │
│                                                                        │
│  [ Identity & Access Management ]                                      │
│        ├─► Argon2id Password Hashing (OWASP recommended parameters)    │
│        ├─► Short-Lived JWT Access Tokens (30 min expiry)               │
│        ├─► Rotating Refresh Tokens (HTTP-only, SameSite=Lax cookies)   │
│        └─► Role-Based Access Control (Viewer / Operator / Admin)       │
│                                                                        │
│  [ Tenant Isolation ]                                                  │
│        └─► SQL Query-Level Organization Scoping (Multi-tenant safe)    │
│                                                                        │
│  [ Webhook & Integration Defense ]                                     │
│        ├─► HMAC-SHA256 Webhook Signature Verification                  │
│        └─► Anti-SSRF Protection (Blocks private IP addresses)          │
│                                                                        │
│  [ Mandatory Simulation Safety Boundary ]                              │
│        ├─► Hard Lock: RECOVERY_SIMULATION_MODE = true                  │
│        ├─► Strict Allowlist Action Registry (No raw shell commands)    │
│        ├─► Cryptographic HMAC-SHA256 Agent Handshake                   │
│        └─► Tamper-Evident SHA-256 Execution Receipts                   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Recovery Simulation Safety Boundary

### Why Simulation Mode is Mandatory
In pilot and evaluation phases, exposing raw infrastructure mutation capabilities introduces severe operational risks (accidental downtime, unintended container destruction, privilege escalation). AutoHeal DevOps enforces `RECOVERY_SIMULATION_MODE=true` as a mandatory safety lock.

### Enforcement Mechanisms:
1. **No Docker Socket Mounting:** Neither `docker-compose.yml` nor `docker-compose.dev.yml` mounts `/var/run/docker.sock` into the backend or worker containers.
2. **No Shell Subprocesses:** The backend contains zero invocations of `os.system()`, `subprocess.Popen(shell=True)`, or arbitrary command execution pipelines.
3. **Restricted Adapter Routing:** When `RECOVERY_SIMULATION_MODE=true`, the `RecoveryExecutor` exclusively routes action requests to `SimulatedAgentClient`.

---

## 3. Strict Allowlist Action Registry

Only predefined, strongly typed actions registered in `backend/app/services/recovery/registry.py` may be scheduled or executed. Any action outside this registry is rejected immediately.

| Action Identifier | Permitted Parameters | Scope & Purpose |
| :--- | :--- | :--- |
| `restart_container` | `service_id` (string), `timeout_seconds` (int, 1–60) | Simulates restarting an unresponsive container process. |
| `restart_pool` | `service_id` (string), `graceful` (boolean) | Simulates recycling a degraded worker connection pool. |
| `scale_service` | `service_id` (string), `replicas` (int, 1–10) | Simulates scaling service replica count to alleviate resource pressure. |

### Parameter Validation
All action parameters are validated against strict JSON schemas. Any payload containing shell metacharacters (`;`, `&`, `|`, `` ` ``, `$`, `\n`) or unauthorized parameters is rejected with an allowlist error.

---

## 4. Cryptographic Agent Authentication & Replay Defense

Communication between the recovery engine and execution agents is cryptographically signed using HMAC-SHA256:

```
Signature = HMAC-SHA256(
    Key = AGENT_SECRET_KEY,
    Message = action_id + ":" + service_id + ":" + action_type + ":" + nonce + ":" + timestamp
)
```

### Protection Against Replay Attacks:
- Every action request contains a unique single-use cryptographic UUID `nonce`.
- Requests include a UTC `timestamp` with a 300-second validity window. Expired or duplicate nonces are rejected.
- Each execution produces a tamper-evident SHA-256 hash receipt combining action parameters, execution duration, exit code, and output summary.

---

## 5. Identity, Authentication & Session Security

### Password Security
- Passwords are encrypted using **Argon2id** (memory cost: 65,536 KiB, iterations: 3, parallelism: 4).
- Plaintext passwords are never logged, persisted, or returned in API responses.

### Token Architecture
- **Access Tokens:** Signed with HMAC-SHA256 using `SECRET_KEY`. Valid for 30 minutes. Transmitted via `Authorization: Bearer <token>` header.
- **Refresh Tokens:** Cryptographically random tokens stored hashed in the database. Issued via secure, HTTP-only cookies (`SameSite=Lax`). Rotating on every use; old tokens are revoked immediately.
- **SSE Tickets:** Single-use, 60-second tickets used to authorize Server-Sent Events streams without exposing long-lived tokens in query strings.

---

## 6. Multi-Tenant Data Isolation

AutoHeal DevOps supports multi-organization tenancy. Tenant isolation is enforced at the database query layer:
- Every tenant resource (`incidents`, `recoveries`, `policies`, `services`, `audit_logs`, `experiments`) includes an `organization_id` foreign key.
- All database queries filter explicitly by `organization_id` extracted from the verified JWT claims of the current authenticated user.
- Cross-tenant data access attempts return HTTP `404 Not Found` or `403 Forbidden`.

---

## 7. Webhook Defense & Anti-SSRF Protections

### Alert Ingestion Webhook Defense
- Inbound webhooks from Alertmanager require HMAC-SHA256 signature verification via the `X-Alertmanager-Signature` header matching `ALERTMANAGER_HMAC_SECRET`.
- Payloads without valid signatures are rejected with HTTP `401 Unauthorized`.

### Outbound Webhook Anti-SSRF
- Outbound notification webhooks (Slack, Microsoft Teams, custom webhooks) resolve DNS hostnames prior to connection.
- Requests targeting private or loopback IP ranges (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`) are blocked, preventing Server-Side Request Forgery against internal infrastructure.

---

## 8. Immutable Audit Logging

Every security-sensitive operation creates an append-only audit record in the `audit_logs` table:
- User login / logout / failed authentication attempts.
- Incident creation, status transition, and manual acknowledgement.
- Recovery approval, dispatch, and post-verification outcome.
- Policy changes, user role modifications, and API key generation.

Audit logs cannot be updated or deleted via the standard API.
