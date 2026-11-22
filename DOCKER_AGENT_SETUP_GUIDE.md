# Restricted Docker Recovery Agent — Setup & Operational Guide

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1 / Phase 16)  
**Applicability:** DevOps Engineers, Evaluators, Site Reliability Engineers  
**Target:** Local Test Environments & Evaluation Meshes  

---

## 1. Overview

The Restricted Docker Recovery Agent (`docker_agent`) is an isolated microservice that executes allowlisted lifecycle operations against approved local test containers. It operates on port `8091` and communicates with the AutoHeal control plane via an authenticated REST API.

---

## 2. Configuration Reference

All settings can be configured via environment variables:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DOCKER_AGENT_ID` | `docker-agent-restricted-01` | Unique identifier for this agent instance. |
| `DOCKER_AGENT_HOST` | `0.0.0.0` | Network interface binding. |
| `DOCKER_AGENT_PORT` | `8091` | Listening port for agent API. |
| `DOCKER_AGENT_SECRET_KEY` | `autoheal_docker_agent_secret_32chars_min` | Shared HMAC secret for verifying request signatures. |
| `DOCKER_AGENT_APPROVED_CONTAINERS`| `autoheal_test_service,test-service` | Comma-separated list of approved container identifiers. |
| `DOCKER_SOCKET_PATH` | `/var/run/docker.sock` | Path to host Docker daemon Unix socket. |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Maximum timeout for Docker restart operations. |
| `MAX_TIMESTAMP_DRIFT_SECONDS` | `300` | Maximum allowable clock drift between control plane and agent. |
| `REPLAY_CACHE_TTL_SECONDS` | `300` | Nonce cache expiration lifespan. |
| `DOCKER_AGENT_ENABLE_MOCK_FALLBACK`| `true` | Allows execution using internal mock engine when socket is unavailable. |

---

## 3. Deployment Method A: Containerized via Docker Compose (Recommended)

To deploy the agent alongside the dedicated test application in an isolated network:

```bash
docker compose -f docker-compose.test-infra.yml up -d
```

### Verification
```bash
docker compose -f docker-compose.test-infra.yml ps
```
Both `autoheal_docker_agent` (port 8091) and `autoheal_test_service` (port 8086) should display state `Up`.

---

## 4. Deployment Method B: Standalone Bare-Metal Process

To run the agent directly on the host machine:

### Step 1: Install Dependencies
From the repository root with virtual environment activated:
```bash
pip install fastapi uvicorn pydantic httpx
```

### Step 2: Start Agent
```bash
python -m docker_agent.main
```
The agent starts listening on `http://0.0.0.0:8091`.

---

## 5. Health & Observability Verification

### 1. Probe Agent Health
```bash
curl -s http://localhost:8091/health | jq
```
Expected output:
```json
{
  "status": "healthy",
  "agent_id": "docker-agent-restricted-01",
  "version": "0.1.0",
  "uptime_seconds": 12,
  "docker_available": true,
  "approved_containers": [
    "autoheal_test_service",
    "test-service"
  ],
  "allowed_operations": [
    "get_container_health",
    "get_container_state",
    "inspect_container",
    "restart_container",
    "verify_container_health"
  ]
}
```

### 2. Inspect Prometheus Metrics
```bash
curl -s http://localhost:8091/metrics
```

### 3. Review Recent Audit Logs
```bash
curl -s http://localhost:8091/api/v1/audit/logs | jq
```

---

## 6. Enabling Control Plane Integration

By default, AutoHeal runs with `RECOVERY_SIMULATION_MODE=true`.

To enable controlled communication between the AutoHeal backend and the restricted agent for the test service:

In your `.env` file or environment:
```env
# Enable restricted agent communication
RESTRICTED_DOCKER_AGENT_ENABLED=true
DOCKER_AGENT_URL=http://localhost:8091
DOCKER_AGENT_SECRET_KEY=autoheal_docker_agent_secret_32chars_min
DOCKER_AGENT_APPROVED_CONTAINERS=autoheal_test_service,test-service
```

> [!IMPORTANT]
> Even when `RESTRICTED_DOCKER_AGENT_ENABLED=true`, the agent will strictly reject any request targeting production containers such as `db`, `redis`, `backend`, or `prometheus`.
