# AutoHeal DevOps — Production Security Checklist

This checklist defines mandatory security controls and verification procedures before exposing the AutoHeal DevOps application to production environments.

---

## 1. Secrets Management & Environment Isolation

- [x] **No Hardcoded Secrets in Codebase**:
  - Codebase scanned for hardcoded API keys, JWT secrets, database passwords, and private certificates.
  - No secret tokens committed to Git history.
- [x] **Git Tracking Guardrails**:
  - `.env`, `.env.local`, `.env.production`, and credential key files (`*.pem`, `*.key`) are included in `.gitignore`.
- [x] **Strong Cryptographic Entropy**:
  - `SECRET_KEY` generated with at least 256 bits of entropy (e.g., `openssl rand -hex 32`).
  - `ALERTMANAGER_HMAC_SECRET` generated with at least 256 bits of entropy.
- [x] **Client-Side Secret Shielding**:
  - Only variables prefixed with `NEXT_PUBLIC_` are exposed to the browser.
  - Backend secrets (`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `ALERTMANAGER_HMAC_SECRET`) remain strictly server-side.

---

## 2. Authentication & Session Security

- [x] **Password Storage**:
  - Passwords hashed using modern **Argon2id** (`argon2-cffi`) with memory-hard parameters resisting GPU/ASIC attacks.
  - Plaintext passwords never logged or returned in API responses.
- [x] **Short-Lived Access Tokens**:
  - JWT access tokens expire after 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES=15`).
  - Tokens signed using HMAC-SHA256 with constant-time verification.
- [x] **Refresh Token Rotation (RTR)**:
  - Refresh tokens are single-use with cryptographic rotation on every refresh.
  - Token lineage tracking: If a revoked or already-used token is presented, the entire token family is invalidated to mitigate replay attacks.
- [x] **Cookie Security**:
  - Refresh tokens delivered via `HttpOnly` cookies, preventing JavaScript access (mitigating XSS).
  - `Secure` flag enforced (`COOKIE_SECURE=true`) ensuring transmission only over HTTPS.
  - `SameSite` attribute configured appropriately (`SameSite=None` with `Secure` for cross-site SaaS deployment; `SameSite=Lax` for same-site custom domain).
- [x] **Session Revocation on Sign-Out**:
  - Calling `/api/v1/auth/logout` explicitly deletes the refresh cookie and marks the token family as revoked in the database.

---

## 3. API Authorization & Access Control (RBAC)

- [x] **Organization Scoping**:
  - Multi-tenant data segregation: Every service, metric, incident, and action is scoped to the user's `organization_id`.
  - Unauthorized cross-organization resource access returns HTTP 403 / 404.
- [x] **Role-Based Access Enforcement**:
  - Operator actions (e.g., approving recovery plans, modifying automated healing policies) require the `admin` or `operator` role.
  - Read-only users (`viewer`) cannot trigger remediations or change service configurations.
- [x] **Protected Route Defaults**:
  - All operational endpoints require a valid Bearer token via FastAPI dependencies (`get_current_active_user`).
  - Unauthenticated requests are rejected immediately with HTTP 401.

---

## 4. Alert Ingestion & Webhook Hardening

- [x] **HMAC-SHA256 Signature Verification**:
  - Inbound Prometheus Alertmanager webhooks are verified via `X-AutoHeal-Signature: sha256=<hex_digest>`.
  - Signatures validated using constant-time comparison (`hmac.compare_digest`) to prevent timing side-channel attacks.
- [x] **Shared Secret Fallback**:
  - Optional `X-Alertmanager-Secret` header supported with constant-time validation.
- [x] **Payload Sanitization**:
  - Webhook payloads validated against strict Pydantic schemas (`AlertmanagerWebhookPayload`).
  - Malformed or oversized payloads rejected before ingestion.

---

## 5. Self-Healing & Infrastructure Safety Controls

- [x] **Simulation Mode Kill-Switch**:
  - `RECOVERY_SIMULATION_MODE=true` is enabled by default in all environments.
  - Real infrastructure commands (Kubernetes restarts, AWS instance reboots, Docker stop/start) are strictly disabled unless explicitly authorized.
- [x] **Audit Trail for Remediations**:
  - Every diagnostic report, suggested action, and approved recovery writes an immutable record to the `audit_logs` table.
  - Records include timestamp, initiating user ID, target service, and action payload.
- [x] **Two-Person Approval Gate**:
  - High-impact recovery actions (e.g., database failovers, production rollbacks) require manual approval via `/api/v1/recoveries/{id}/approve`.

---

## 6. Container & Runtime Hardening

- [x] **Non-Root Execution**:
  - Backend Docker container creates and executes under unprivileged system user `autoheal:autoheal` (`UID 10001`).
- [x] **Minimal Base Image**:
  - Utilizes `python:3.11-slim` with multi-stage build caching, omitting unnecessary system utilities, compilers, and shells.
- [x] **Configurable Reverse Proxy Trust**:
  - Uvicorn configured with `--forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1,::1}"`.
  - Wildcard proxy trust (`*`) is strictly rejected in production environments to prevent client IP and scheme spoofing.
- [x] **Clean Process Termination**:
  - Asyncpg connection pool explicitly drained via `engine.dispose()` on FastAPI application shutdown.

---

## 7. Transport Security & Network Defense

- [x] **End-to-End TLS**:
  - All public traffic encrypted via TLS 1.3 on both frontend (Vercel) and backend (Render/Railway).
- [x] **Cross-Origin Resource Sharing (CORS)**:
  - Backend strictly whitelists explicit frontend origins (no wildcard `*` with credentials).
  - Whitelist supports custom domains and Vercel preview environments.
- [x] **PostgreSQL TLS Verification**:
  - PostgreSQL connections enforce SSL (`sslmode=require` auto-translated to `ssl=require` for asyncpg).
  - Supports `verify-ca` and `verify-full` with custom CA certificate validation (`DB_SSL_CA_CERT`).
  - Disabling SSL (`disable`) in production or staging is strictly rejected by configuration validation.
- [x] **Redis TLS Certificate Verification**:
  - Redis connections support TLS via `rediss://` protocol.
  - Enforces `ssl.CERT_REQUIRED` and hostname verification (`ssl_check_hostname=True`).
  - Supports custom CA certificates (`REDIS_SSL_CA_CERTS`) and client mTLS certificates.
  - Disabling certificate verification (`none`) in production or staging is strictly rejected.
