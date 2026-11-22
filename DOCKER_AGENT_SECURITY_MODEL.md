# Restricted Docker Recovery Agent — Security Model & Threat Analysis

**Document Version:** 1.0.0  
**Phase:** Phase 16 — Controlled Real Infrastructure Integration & Production Readiness  
**Target Component:** `docker_agent/`  
**Security Level:** Least-Privilege Controlled Sandbox  

---

## 1. Security Philosophy & Architectural Tenets

1. **The Backend Is Not Trusted as the Sole Boundary:** Even if the FastAPI control plane were fully compromised, the Restricted Docker Agent must independently validate and reject unapproved operations.
2. **Zero Socket Access for Application Layers:** Neither the web frontend, FastAPI backend, Celery workers, nor databases receive access to `/var/run/docker.sock`.
3. **No Shell Subprocesses:** The agent interacts with Docker exclusively via structured Docker Engine HTTP APIs. No `sh -c`, `bash`, or shell wrappers are ever invoked.
4. **Strict Server-Side Allowlists:** Container names and operations are validated against rigid allowlists enforced on the agent.
5. **Two-Stage Verification:** A successful container restart (`exit_code=0`) is never equated with SLA restoration.
6. **AI Never Independently Authorizes Remediations:** AI is restricted to diagnostic analysis and recommendation; human-in-the-loop operator approval is mandatory.

---

## 2. Threat Model & Attack Surface Analysis

| Threat Identifier | Threat Vector | Impact | Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **THREAT-1: Host Root Escalation via Docker Socket** | Attacker uses Docker socket access to mount host filesystem or escape container boundaries. | Complete host compromise. | FastAPI backend has **zero** socket access. Docker socket is mounted strictly into the decoupled `docker_agent` container. Agent enforces strict API parameter constraints; container creation and mount APIs are completely absent from the allowlist. |
| **THREAT-2: Command & Argument Injection** | Attacker injects shell metacharacters (`;`, `|`, `&&`, `$()`) into container names or parameters. | Arbitrary command execution on host. | Container identifiers validated against regex `^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$`. Prohibited character pattern `[;&|`$><\n\r\t\\]` rejects all metacharacters. Typed JSON parameters only. |
| **THREAT-3: Targeted Destruction of Production Services** | Attacker or faulty policy targets `db`, `redis`, `backend`, or `prometheus`. | Cascading infrastructure outage and data loss. | Server-side container allowlist strictly permits only designated test containers (`autoheal_test_service`). A hardcoded blacklist (`CRITICAL_PROTECTED_CONTAINERS`) explicitly rejects core stack containers. |
| **THREAT-4: Request Forgery & Replay Attacks** | Man-in-the-middle captures and replays a valid recovery approval request. | Unauthorized repeated container recycling (DoS/flapping). | Canonical HMAC-SHA256 signature verification over canonical byte serialization. Every request requires a unique UUID `nonce` stored in a TTL replay cache (300s). Timestamps older than 300s are rejected. |
| **THREAT-5: Premature Resolution (Split-Brain)** | Container restarts successfully, but internal application fails to initialize (crash loop, 503). | Incident marked resolved while outage persists. | Mandatory Two-Stage Verification: Stage 1 inspects container lifecycle state; Stage 2 independently probes application HTTP `/health` endpoint. Incident is escalated if Stage 2 fails. |
| **THREAT-6: Autonomous Rogue AI Execution** | AI hallucinates an unsafe remediation or is prompt-injected into issuing destructive commands. | Unintended service disruption. | AI subsystem has zero execution privileges. Remediations require cryptographic approval signed by an authenticated Operator/Admin user. |

---

## 3. Cryptographic Authentication & Nonce Replay Defense

Every request dispatched to `POST /api/v1/actions/execute` must contain:

1. **`action_id`:** Unique UUID assigned by the AutoHeal control plane.
2. **`target_container`:** Target service name (must match `APPROVED_CONTAINERS`).
3. **`action_type`:** Allowlisted operation (must match `ALLOWED_OPERATIONS`).
4. **`parameters`:** Validated JSON parameter dictionary.
5. **`nonce`:** Cryptographic single-use UUID.
6. **`timestamp`:** ISO-8601 UTC timestamp.
7. **`signature`:** Hex-encoded HMAC-SHA256 signature calculated as:

$$\text{CanonicalString} = \text{action\_id} : \text{target\_container} : \text{action\_type} : \text{SortedJSON(parameters)} : \text{nonce} : \text{timestamp}$$

$$\text{Signature} = \text{HMAC-SHA256}(\text{Key}=\text{AGENT\_SECRET\_KEY}, \text{Message}=\text{CanonicalString})$$

### Replay Prevention Mechanics
- The agent maintains an in-memory sliding-window cache of seen nonces: `_SEEN_NONCES: Dict[str, float]`.
- Upon receiving a request:
  1. The agent purges nonces older than `REPLAY_CACHE_TTL_SECONDS` (300 seconds).
  2. The agent checks if `timestamp` drift exceeds `MAX_TIMESTAMP_DRIFT_SECONDS` (300 seconds). If $|t_{\text{agent}} - t_{\text{request}}| > 300$, the request is rejected with HTTP 401.
  3. The agent checks if `nonce` is already present in `_SEEN_NONCES`. If present, the request is rejected with HTTP 401 as a replay attack.
  4. If signature matches and nonce is fresh, the nonce is recorded with the current epoch timestamp.

---

## 4. Operation & Container Allowlists

The Restricted Docker Agent rejects any request that violates either of the following two server-side allowlists:

### Container Allowlist (`APPROVED_CONTAINERS`)
- Permitted in Phase 16: `autoheal_test_service`, `test-service`
- Prohibited (`CRITICAL_PROTECTED_CONTAINERS`): `db`, `postgres`, `redis`, `backend`, `frontend`, `celery_worker`, `celery_beat`, `prometheus`, `alertmanager`, `grafana`, `node_exporter`, `cadvisor`, `otel_collector`, `jaeger`.
- Any unlisted container receives HTTP 403 Forbidden.

### Operation Allowlist (`ALLOWED_OPERATIONS`)
- `inspect_container`: Read-only container metadata.
- `get_container_state`: Read-only lifecycle state.
- `get_container_health`: Read-only health check state.
- `restart_container`: Controlled graceful restart (bounded grace: 1–60s).
- `verify_container_health`: Probes application `/health` endpoint.
- **Explicitly Excluded:** `docker run`, `docker create`, `docker rm`, `docker exec`, `docker build`, `docker pull`, `docker push`, `docker volume rm`.

---

## 5. Residual Security Risks & Production Graduation Requirements

### Residual Risk of Mounting `/var/run/docker.sock`
> [!WARNING]
> While isolating the Docker socket to `autoheal_docker_agent` eliminates backend vulnerability, mounting `/var/run/docker.sock` into any container grants that container root equivalent access to the host Docker daemon. If a remote code execution vulnerability were discovered in the agent daemon itself, the attacker could theoretically access the host.

### Graduation Requirements for Production Infrastructure:
Before deploying AutoHeal to production infrastructure outside local test meshes:
1. **Docker Socket Proxy:** Interpose a read-only Docker socket proxy (such as `tecnativa/docker-socket-proxy`) that strips all POST endpoints except `/containers/{name}/restart`.
2. **Container Labels Scoping:** Restrict the agent to only containers tagged with `autoheal.managed=true`.
3. **Mutual TLS (mTLS):** Transition communication between backend and agent from shared-secret HMAC to client-authenticated mTLS with ephemeral X.509 certificates issued by the AutoHeal internal CA.
4. **AppArmor / SELinux Profiles:** Apply strict AppArmor/SELinux profiles to the agent container preventing ptrace, raw socket creation, and filesystem traversal.
