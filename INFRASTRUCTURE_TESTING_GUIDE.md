# AutoHeal DevOps — Phase 7 Infrastructure Testing Guide

## 1. Overview & Test Strategy

Phase 7 introduces 10 rigorous, non-destructive test scenarios implemented in `backend/tests/test_infrastructure_integration.py`. These tests validate infrastructure security boundaries, cryptographic signing, policy gates, and fail-safe behavior in an isolated test environment without touching live production infrastructure.

All tests utilize an in-memory transactional SQLite database (`sqlite+aiosqlite:///:memory:`) and mocked or simulated infrastructure adapters (`RECOVERY_SIMULATION_MODE=true`).

---

## 2. The 10 Validated Infrastructure Scenarios

| Scenario # | Test Function | Verified Behavior | Failure Mode Tested |
| :---: | :--- | :--- | :--- |
| **1** | `test_agent_registration_and_heartbeat` | Agent registers, generates 256-bit secret, authenticates HMAC heartbeats | Unauthenticated / unregistered heartbeat rejection |
| **2** | `test_agent_revocation_enforcement` | Revoking an agent immediately invalidates secret and status becomes `revoked` | 403 Forbidden on revoked agent heartbeats |
| **3** | `test_nonce_replay_rejection` | Cryptographic nonces cannot be replayed across multiple requests | 401 Unauthorized on duplicate nonce attack |
| **4** | `test_clock_drift_rejection` | Timestamps diverging > 300s from server time are rejected | 401 Unauthorized on delayed or future timestamp |
| **5** | `test_policy_engine_evaluation` | Allowlist, cooldown (< 900s), retry limits (> 3), and operator roles are enforced | Prohibited actions, viewer execution, and flapping rejected |
| **6** | `test_restricted_docker_adapter_injection_defense` | Container names with `;`, `&`, `\|`, `$`, `..` are blocked before execution | `SecurityViolationError` on shell metacharacters |
| **7** | `test_k8s_adapter_namespace_isolation` | System namespaces (`kube-system`) and unapproved deployments are blocked | `K8sSecurityViolationError` on unauthorized namespace |
| **8** | `test_ai_diagnosis_schemas_and_prompt_injection` | Enhanced schemas verified; prompt injection prefixes do not alter allowlist action | AI recommendations outside allowlist sanitized to safe actions |
| **9** | `test_multi_tenant_agent_and_policy_isolation` | Tenant Alpha cannot query, heartbeat, or revoke Tenant Beta's agents or policies | 404 Not Found cross-tenant leakage prevention |
| **10** | `test_safe_failure_state_handling` | Execution or verification failures escalate incidents safely without infinite loop | Transition to `failed` and escalation to on-call |

---

## 3. Test Execution Commands

### Run Dedicated Phase 7 Suite
```bash
# Activate virtual environment
.venv\Scripts\activate

# Run Phase 7 infrastructure integration tests
pytest backend/tests/test_infrastructure_integration.py -v
```

### Run Full Backend Quality & Regression Suite
```bash
# Validate Python syntax across all modules
python -m compileall -q backend/app backend/tests

# Run all 163 pytest unit, integration, and E2E tests
pytest backend/tests -v --durations=10
```

### Run Frontend Verification Suite
```bash
# Typecheck Next.js & React components
npx tsc --noEmit

# Run ESLint validation
npx eslint .

# Test production build
npm run build
```

### Validate Docker & Compose Configurations
```bash
docker compose config
```
