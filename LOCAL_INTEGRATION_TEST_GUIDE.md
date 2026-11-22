# Local Integration Testing Guide — Restricted Docker Recovery

**Version:** 1.0.0 (Release Candidate v0.1.0-rc1 / Phase 16)  
**Applicability:** Test Engineers, QA, DevOps Evaluators  
**Scope:** Isolated Test Network (`autoheal_test_network`)  

---

## 1. Prerequisites & Environment Isolation

This integration test operates strictly within a dedicated Docker bridge network (`autoheal_test_network`).
- **Target Container:** `autoheal_test_service` (port 8086 on host, port 8080 internal).
- **Restricted Agent:** `autoheal_docker_agent` (port 8091).
- **Core Stack Safety:** The test environment has zero connections to PostgreSQL, Redis, or existing AutoHeal volumes.

---

## 2. Step 1: Start the Isolated Test Mesh

From the root of the repository:
```bash
docker compose -f docker-compose.test-infra.yml up -d
```

Verify that both test services are active:
```bash
docker compose -f docker-compose.test-infra.yml ps
```

---

## 3. Step 2: Verify Initial Service Health

Probe the test microservice health endpoint:
```bash
curl -i http://localhost:8086/health
```
**Expected Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"healthy","service":"autoheal_test_service","message":"Operational","uptime_seconds":15}
```

---

## 4. Step 3: Inject Controlled Failure

Inject a simulated degradation into `autoheal_test_service`:
```bash
curl -X POST http://localhost:8086/chaos/degrade
```

Re-check the health endpoint:
```bash
curl -i http://localhost:8086/health
```
**Expected Response:**
```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"degraded","service":"autoheal_test_service","message":"Simulated connection pool failure"}
```

---

## 5. Step 4: Dispatch Authenticated Recovery Action

Execute a signed recovery request via the Python helper script or curl:

```bash
python -c "
import urllib.request, json, uuid, hmac, hashlib
from datetime import datetime, timezone

SECRET = 'autoheal_docker_agent_secret_32chars_min'
now = datetime.now(timezone.utc).isoformat()
nonce = uuid.uuid4().hex
action_id = f'act-test-{uuid.uuid4().hex[:8]}'

params = {'timeout_seconds': 10}
sorted_params = json.dumps(params, sort_keys=True, separators=(',', ':'))
canonical = f'{action_id}:autoheal_test_service:restart_container:{sorted_params}:{nonce}:{now}'
sig = hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()

payload = {
    'action_id': action_id,
    'target_container': 'autoheal_test_service',
    'action_type': 'restart_container',
    'parameters': params,
    'timeout_seconds': 30,
    'nonce': nonce,
    'timestamp': now,
    'signature': sig,
    'correlation_id': 'corr-manual-test-01'
}

req = urllib.request.Request(
    'http://localhost:8091/api/v1/actions/execute',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json'}
)

with urllib.request.urlopen(req) as resp:
    print('STATUS:', resp.getcode())
    print(json.dumps(json.loads(resp.read().decode()), indent=2))
"
```

**Expected Response:**
```json
{
  "action_id": "act-test-...",
  "target_container": "autoheal_test_service",
  "action_type": "restart_container",
  "status": "success",
  "exit_code": 0,
  "duration_ms": 1150,
  "stdout": "[DOCKER_ENGINE] Container 'autoheal_test_service' restarted cleanly.",
  "evidence_receipt_hash": "a1b2c3d4...",
  "is_mocked": false
}
```

---

## 6. Step 5: Verify Application Health Restoration

Verify that restarting the container has reset `autoheal_test_service` back to a healthy state:
```bash
curl -i http://localhost:8086/health
```
**Expected Response:** HTTP 200 OK (`status: healthy`).

---

## 7. Step 6: Validate Security Boundaries

### Security Test A: Replay Attack Rejection
Re-send the identical payload from Step 4 without changing the `nonce`:
```bash
# Re-running the identical request with reused nonce
```
**Expected Response:** HTTP `401 Unauthorized` (`Detail: Nonce '...' has already been processed (replay detected)`).

### Security Test B: Core Infrastructure Protection
Attempt to target the PostgreSQL database:
```bash
python -c "
import urllib.request, json, uuid, hmac, hashlib
from datetime import datetime, timezone

SECRET = 'autoheal_docker_agent_secret_32chars_min'
now = datetime.now(timezone.utc).isoformat()
nonce = uuid.uuid4().hex
action_id = 'act-attack-db'
params = {}
canonical = f'{action_id}:db:restart_container:{{}}:{nonce}:{now}'
sig = hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()

payload = {
    'action_id': action_id,
    'target_container': 'db',
    'action_type': 'restart_container',
    'parameters': params,
    'nonce': nonce,
    'timestamp': now,
    'signature': sig
}

try:
    req = urllib.request.Request('http://localhost:8091/api/v1/actions/execute', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    print('REJECTED WITH STATUS:', e.code)
    print(e.read().decode())
"
```
**Expected Response:** HTTP `403 Forbidden` (`Detail: Container 'db' is a protected core infrastructure service. Recovery operations are strictly forbidden.`).

---

## 8. Step 7: Clean Shutdown

When testing is complete:
```bash
docker compose -f docker-compose.test-infra.yml down
```
All test containers are terminated and networks removed.
