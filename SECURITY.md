# AutoHeal DevOps — Security Policy & Remediation Guide

## 1. Overview & Security Posture

AutoHeal DevOps enforces a defense-in-depth security architecture designed to protect production telemetry, prevent unauthorized infrastructure modification, and isolate multi-tenant organizational data.

---

## 2. Authentication & Session Management

### 2.1 Password Hashing (Argon2id)
* User passwords are hashed using **Argon2id** via `passlib.context.CryptContext(schemes=["argon2"])`.
* Protects against GPU and ASIC brute-force attacks by leveraging memory-hard computational complexity.
* Plaintext passwords are never logged, persisted, or included in serialization responses.

### 2.2 Short-Lived JWT Access Tokens
* Access tokens are signed using `PyJWT` with the `HS256` algorithm and the server-side `SECRET_KEY`.
* Default expiration is strictly bounded to **15 minutes** (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`).
* Token claims include: `sub` (User UUID), `email`, `role`, `org_id`, `jti` (Token UUID), `iat`, `exp`, and `type="access"`.

### 2.3 Refresh Token Rotation (RTR) & Replay Attack Defense
* Refresh tokens provide ~288 bits of cryptographic entropy generated via `secrets.token_urlsafe(48)`.
* Only the SHA-256 hash (`hash_token(raw_token)`) is persisted in PostgreSQL to protect against read-only database compromise.
* **Token Family Tracking**: Each login creates a `family_id`. When a refresh token is used, it is revoked, and a child token is issued in the same family.
* **Replay Attack Detection**: If a revoked refresh token is presented again, the authentication engine flags a security breach, invalidates **all** active tokens in that family immediately, logs a `token_replay_detected` audit event, and terminates sessions across devices.

### 2.4 Secure Cookie Policy
* In production and staging, refresh tokens are transported via `HttpOnly`, `Secure` cookies with `SameSite=none` (or `SameSite=lax` where appropriate).
* JavaScript cannot access the refresh cookie, mitigating Cross-Site Scripting (XSS) credential theft.

---

## 3. Authorization & Multi-Tenant Isolation

### 3.1 Role-Based Access Control (RBAC)
AutoHeal DevOps enforces three hierarchical roles:

| Role | Permissions | Endpoints Allowed |
| :--- | :--- | :--- |
| **Viewer** | Read-only access to services, telemetry, incidents, and analytics. | `GET /api/v1/services`, `GET /api/v1/incidents`, `GET /api/v1/analytics/*`, `GET /api/v1/settings` |
| **Operator** | Read-only access plus recovery plan approval, rejection, and manual simulated execution. | All Viewer endpoints + `POST /api/v1/recoveries/{id}/approve`, `POST /api/v1/recoveries/{id}/reject`, `POST /api/v1/recoveries/{id}/execute` |
| **Admin** | Full operational and governance control, including organization settings updates and user management. | All Operator endpoints + `PATCH /api/v1/settings` (workspace rename), user provisioning |

Any attempt by a Viewer to execute or approve a recovery action fails closed with `403 Forbidden`.

### 3.2 Tenant Isolation
* All authenticated requests resolve `current_user` and `current_org`.
* Database queries strictly filter by `organization_id == current_org.id`.
* Querying or attempting to download incident reports belonging to another organization returns `404 Not Found`.

---

## 4. API & Network Security

### 4.1 CORS Policy
* Cross-Origin Resource Sharing is restricted via `CORSMiddleware`.
* Allowed origins are configured via `CORS_ORIGINS`.
* Wildcards (`*`) are prohibited in production.

### 4.2 Rate Limiting & Input Validation
* Sensitive authentication endpoints (`/login`, `/register`, `/forgot-password`) enforce strict request-rate limits to mitigate credential stuffing.
* All payloads are validated using Pydantic schemas with type enforcement, string length restrictions, and regex validation.
* Request body size is limited to prevent denial-of-service memory exhaustion.

### 4.3 Error Handling & Information Disclosure
* Production exceptions are captured and converted to sanitized JSON error responses (`{"detail": "..."}`).
* Database connection strings, stack traces, and internal server internals are never exposed to clients.

---

## 5. Secret Management & Legacy Secret Exposure Documentation

### 5.1 Exposure Disclosure (Development History)
* **Secret Identifier**: `autoheal_alertmanager_webhook_hmac_secret_key_12345`
* **Historical Context**: During early prototyping and initial development commits (Phases 3–4), this placeholder string was used as a shared secret for local Alertmanager webhook tests.
* **Git History Preservation Policy**: In accordance with enterprise repository guidelines, Git history has **not** been rewritten or force-pushed.
* **Current Remediation**:
  1. The hardcoded placeholder has been removed from application defaults.
  2. The backend configuration (`backend/app/config.py`) now includes an automated security validator:
     ```python
     if self.APP_ENV in ("production", "staging"):
         insecure_hmac_defaults = {
             "autoheal_alertmanager_webhook_hmac_secret_key_12345",
             "autoheal_dev_alertmanager_webhook_secret_32chars",
             "",
         }
         if not self.ALERTMANAGER_HMAC_SECRET or self.ALERTMANAGER_HMAC_SECRET in insecure_hmac_defaults:
             raise ValueError("ALERTMANAGER_HMAC_SECRET is missing or using an insecure default value.")
     ```
  3. Production and staging deployments will refuse to start if this legacy secret or default placeholder is used.

### 5.2 Secret Rotation Instructions for Production
To rotate the Alertmanager HMAC/Bearer secret in any deployed environment:

1. **Generate a High-Entropy Secret**:
   ```bash
   openssl rand -hex 32
   ```
2. **Update Backend Environment**:
   Set `ALERTMANAGER_HMAC_SECRET` in the backend environment variables:
   ```bash
   ALERTMANAGER_HMAC_SECRET=<new_secret_from_step_1>
   ```
3. **Update Alertmanager Configuration**:
   Update `alertmanager.yml` or the mounted secret file:
   ```yaml
   receivers:
     - name: "autoheal-webhook"
       webhook_configs:
         - url: "http://autoheal-api:8000/api/v1/alerts/webhook"
           send_resolved: true
           http_config:
             bearer_token: "<new_secret_from_step_1>"
   ```
4. **Reload Services**:
   Reload Alertmanager (`curl -X POST http://alertmanager:9093/-/reload`) and restart the FastAPI backend.

---

## 6. Infrastructure & Recovery Safety

### 6.1 Simulation Enforcement
* `RECOVERY_SIMULATION_MODE=true` is enforced across all non-production environments.
* Simulated recovery adapters execute synthetic remediation receipts without invoking operating system commands.

### 6.2 Zero Docker Socket Exposure
* The Docker daemon socket (`/var/run/docker.sock` or `//./pipe/docker_engine`) is **strictly NEVER** mounted into any application container.
* No container has root access or administrative privileges to execute arbitrary host commands.

### 6.3 Action Allowlist
Only actions explicitly registered in `APPROVED_RECOVERY_ACTIONS` are permitted:
* `restart_service`
* `clear_cache`
* `scale_service`
* `restore_health`
* `rollback_release`

Any recommendation outside this set is automatically rejected by the AI adapter and replaced with safe defaults.
