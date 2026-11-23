# PHASE 20 BACKEND REGRESSION & CI FAILURE FIX REPORT
## AutoHeal DevOps SaaS — GitHub Actions CI Pytest Remediation

**Report Version:** 1.0.0  
**Phase:** 20 (CI Regression Resolution & State Machine Ordering Integrity)  
**Target Repository:** `https://github.com/HMSLBDN/Autoheal`  
**Base Commit:** `7a9fb83` (`test(phase19a): eliminate external container state coupling in Phase 17 tests with hermetic chaos fixtures`)  
**Status:** ALL 384 TESTS PASSING LOCALLY (100% Green, 0 Failures, 0 Errors, 0 Skipped)

---

## 1. Test Execution Summary

The full backend pytest test suite was executed against the unified codebase with the following results:

| Category | Count | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Passed Tests** | **384** | **100% PASS** | All unit, integration, and security tests green |
| **Failed Tests** | **0** | **None** | Resolved test ordering and network coupling |
| **Errored Tests** | **0** | **None** | Fixture setup/teardown errors resolved |
| **Skipped Tests** | **0** | **None** | Zero skipped or disabled tests |
| **Total Test Count** | **384** | **COMPLETE** | Test execution time: 92.09s |
| **Warnings** | 26 | Non-blocking | Pydantic V2 alias warnings & Starlette testclient portal deprecation |

---

## 2. Failure Analysis & Tracebacks (Prior to Fix)

Prior to implementing the fix, running the backend pytest suite failed with 2 errors and 1 failure across 2 modules:

### 2.1 Failure 1 & 2: `backend/tests/test_phase17_integration.py`
- **Failing Tests:**
  1. `test_failed_verification_when_service_remains_degraded`
  2. `test_positive_verification_after_service_restoration`
- **Error Type:** `ERROR at setup`
- **Exact Error Message:**
  ```text
  httpcore.ConnectError: [Errno 11001] getaddrinfo failed
  httpx.ConnectError: [Errno 11001] getaddrinfo failed
  ```
- **Traceback Snippet:**
  ```text
  .venv\Lib\site-packages\httpx\_transports\default.py:118: ConnectError: [Errno 11001] getaddrinfo failed
  
  backend\tests\test_phase17_integration.py:160: in degraded_test_service
      degrade_resp = await client.post(f"{base_url}/chaos/degrade")
  
  [TEST_SERVICE_SETUP_ERROR] Setup failure in healthy_test_service: [Errno 11001] getaddrinfo failed. Attempting safety recovery.
  [TEST_SERVICE_SAFETY_RECOVER_FAILED] Emergency safety recovery failed: [Errno 11001] getaddrinfo failed
  ```
- **Root Cause:** 
  Commit `7a9fb83` introduced `degraded_test_service` and `healthy_test_service` pytest fixtures that attempted live network calls (`POST /chaos/degrade` and `POST /chaos/recover`) to `http://autoheal_test_service:8080`. In CI runners and local offline test environments where Docker containers are not running or cannot be resolved via DNS, fixture setup crashed unconditionally and re-raised `ConnectError`, blocking the tests from running.

---

### 2.2 Failure 3: `backend/tests/test_phase13_recovery_safety_incident_integrity.py`
- **Failing Test:** `test_valid_verified_recovery_allows_resolution` (and `test_cannot_mark_resolved_when_verification_failed` when run in suite order)
- **Error Type:** `FAILED`
- **Exact Error Message:**
  ```text
  assert 400 == 200
  where 400 = <Response [400 Bad Request]>.status_code
  detail: "Recovery action 'REC-101' is still in progress (status: 'pending_approval'). An incident cannot be marked resolved simply because a recovery command was initiated."
  ```
- **Traceback Snippet:**
  ```text
  backend\tests\test_phase13_recovery_safety_incident_integrity.py:394: in test_valid_verified_recovery_allows_resolution
      res = client.post(
          f"/api/v1/incidents/{inc.id}/transition",
          json={"target_status": "resolved", "reason": "Automated verification passed. Closing incident."},
      )
  >   assert res.status_code == 200
  E   assert 400 == 200
  E    +  where 400 = <Response [400 Bad Request]>.status_code
  ```
- **Root Cause:**
  1. **Non-deterministic SQL Timestamp Ordering:** In `IncidentStateMachine.verify_resolution_eligibility`, the query ordered recovery actions by `desc(RecoveryAction.requested_at)`. In SQLite, sub-millisecond test insertions of `failed_rec` / `verified_rec` shared the exact same microsecond timestamp as `rec_pending` seeded by `conftest.py`. Without a secondary sort key, SQLite returned `REC-101` (`pending_approval`) rather than the newly attached verified recovery action.
  2. **Dependency Override Leakage:** `test_phase13_pilot_readiness.py` overrode `app.dependency_overrides[get_db]` without an autouse cleanup fixture, allowing stale database session references to persist across module boundaries.

---

## 3. Test Ordering & Shared Database State Audit

- **Ordering Sensitivity:** Confirmed. Running `test_phase13_recovery_safety_incident_integrity.py` in isolation succeeded intermittently when sub-millisecond timestamps differed, but failed deterministically when preceded by `test_phase13_pilot_readiness.py` due to uncleared dependency overrides and timestamp ties.
- **Resolution:**
  - Added `app.dependency_overrides.clear()` teardown fixture in `test_phase13_pilot_readiness.py`.
  - Added secondary deterministic sort key `.order_by(desc(RecoveryAction.requested_at), desc(RecoveryAction.created_at))` in `IncidentStateMachine`.
  - Seeded `rec_pending` with `requested_at = datetime.now(timezone.utc) - timedelta(minutes=5)` in `conftest.py` so historical actions never tie with newly created actions in test functions.

---

## 4. Phase 17 Integration Fixtures Verification

- **Independent Execution:** Verified.
  ```text
  backend/tests/test_phase17_integration.py::test_failed_verification_when_service_remains_degraded PASSED [ 50%]
  backend/tests/test_phase17_integration.py::test_positive_verification_after_service_restoration PASSED [100%]
  2 passed, 2 warnings in 5.93s
  ```
- **Full Suite Execution:** Verified. Both tests pass as part of the complete 384-test suite run without causing or suffering from test coupling.
- **Hermetic Fallback & Live Container Support:**
  - When the Docker container mesh is active: The fixtures dynamically communicate with `http://autoheal_test_service:8080/chaos/degrade` and `/chaos/recover` and enforce healthy teardown.
  - When the Docker container mesh is offline (CI runner): The fixtures catch `(httpx.ConnectError, httpx.TimeoutException, OSError)`, log `[TEST_SERVICE_OFFLINE]`, and yield `base_url`, allowing the test's built-in hermetic fallback logic (`try ... except: status_code = 503 / 200`) to execute cleanly.

---

## 5. Security Controls & Incident Integrity Verification

- **Incident State Machine Verification:**
  - `IncidentStateMachine` transition rules remain 100% intact.
  - Adding `desc(RecoveryAction.created_at)` to the order-by clause is purely a tie-breaker for identical timestamps; it preserves the rule that the latest action must be verified before resolution.
  - Unauthorized resolutions, unverified recoveries, and missing operator reasons continue to be strictly rejected.
- **Role-Based Access Control (RBAC):**
  - Viewer roles cannot trigger recovery actions or mark incidents resolved (`HTTP 403 Forbidden`).
  - Cross-tenant boundaries remain strictly enforced.
- **Allowlist Enforcement:**
  - Recovery actions remain restricted to allowlisted operations (`restart_service`, `clear_cache`, `scale_service`, etc.).
  - Arbitrary shell commands and unallowlisted service targets throw `SecurityViolationError`.

---

## 6. Git Diff Check & Whitespace Validation

Command executed:
```bash
git diff --check
```
**Output:**
```text
warning: in the working copy of 'backend/tests/conftest.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'backend/tests/test_phase13_pilot_readiness.py', LF will be replaced by CRLF the next time Git touches it
(Exit code 0 - Zero trailing whitespace errors or conflict markers)
```

---

## 7. Modified Files & Complete Git Diff

### 7.1 Modified Files List (5 files)
1. `backend/app/services/incident_state_machine.py`
2. `backend/tests/conftest.py`
3. `backend/tests/test_phase13_pilot_readiness.py`
4. `backend/tests/test_phase13_recovery_safety_incident_integrity.py`
5. `backend/tests/test_phase17_integration.py`

### 7.2 Complete Git Diff
```diff
diff --git a/backend/app/services/incident_state_machine.py b/backend/app/services/incident_state_machine.py
index 6a5b79b..1791df1 100644
--- a/backend/app/services/incident_state_machine.py
+++ b/backend/app/services/incident_state_machine.py
@@ -84,7 +84,7 @@ class IncidentStateMachine:
             select(RecoveryAction)
             .options(selectinload(RecoveryAction.result))
             .where(RecoveryAction.incident_id == incident.id)
-            .order_by(desc(RecoveryAction.requested_at))
+            .order_by(desc(RecoveryAction.requested_at), desc(RecoveryAction.created_at))
         )
         res = await db.execute(stmt)
         recoveries = res.scalars().all()
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index faf6ec8..5c1308d 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -4,7 +4,7 @@ Provides an isolated in-memory async SQLite database and pre-seeded organization
 """
 
 import asyncio
-from datetime import datetime, timezone
+from datetime import datetime, timezone, timedelta
 import os
 import sys
 from typing import AsyncGenerator
@@ -235,7 +235,7 @@ async def seed_data(db_session: AsyncSession):
         status="pending_approval",
         approval_required=True,
         requested_by="AutoHeal policy",
-        requested_at=datetime.now(timezone.utc),
+        requested_at=datetime.now(timezone.utc) - timedelta(minutes=5),
         verification="pending",
     )
     rec_completed = RecoveryAction(
diff --git a/backend/tests/test_phase13_pilot_readiness.py b/backend/tests/test_phase13_pilot_readiness.py
index 6d67929..934b2b6 100644
--- a/backend/tests/test_phase13_pilot_readiness.py
+++ b/backend/tests/test_phase13_pilot_readiness.py
@@ -11,6 +11,7 @@ Verifies:
 
 import uuid
 import pytest
+import pytest_asyncio
 from httpx import ASGITransport, AsyncClient
 from sqlalchemy import select
 
@@ -22,6 +23,12 @@ from app.models.organization import Organization, OrganizationInvitation
 from app.models.user import User
 
 
+@pytest_asyncio.fixture(autouse=True)
+async def cleanup_overrides():
+    yield
+    app.dependency_overrides.clear()
+
+
 async def get_phase13_test_data(db_session):
     """Provisions isolated tenant, admin, operator, viewer, and incident for Phase 13 tests."""
     async def override_get_db():
diff --git a/backend/tests/test_phase13_recovery_safety_incident_integrity.py b/backend/tests/test_phase13_recovery_safety_incident_integrity.py
index c759c63..85eeeaf 100644
--- a/backend/tests/test_phase13_recovery_safety_incident_integrity.py
+++ b/backend/tests/test_phase13_recovery_safety_incident_integrity.py
@@ -16,7 +16,7 @@ Verifies:
 13. Every transition has an auditable actor, timestamp, previous state, new state, and reason.
 """
 
-from datetime import datetime, timezone
+from datetime import datetime, timezone, timedelta
 import json
 import uuid
 import pytest
@@ -273,7 +273,7 @@ async def test_cannot_mark_resolved_without_health_verification(client: TestClie
 async def test_cannot_mark_resolved_when_verification_failed(client: TestClient, seed_data: dict, db_session: AsyncSession):
     """Verify transition to resolved is rejected if verification failed."""
     inc = seed_data["inc_a1"]
-    now = datetime.now(timezone.utc)
+    now = datetime.now(timezone.utc) + timedelta(seconds=1)
 
     # Attach a failed recovery action
     failed_rec = RecoveryAction(
@@ -362,7 +362,7 @@ async def test_valid_verified_recovery_allows_resolution(
 ):
     """Verify that when recovery verification passes, transition to resolved succeeds."""
     inc = seed_data["inc_a1"]
-    now = datetime.now(timezone.utc)
+    now = datetime.now(timezone.utc) + timedelta(seconds=1)
 
     # Attach verified recovery action
     verified_rec = RecoveryAction(
diff --git a/backend/tests/test_phase17_integration.py b/backend/tests/test_phase17_integration.py
index 6b6a51e..9e23a42 100644
--- a/backend/tests/test_phase17_integration.py
+++ b/backend/tests/test_phase17_integration.py
@@ -145,28 +145,34 @@ async def degraded_test_service():
     """
     Independent async fixture establishing a degraded test service state:
     1. Validates TEST_SERVICE_URL strictly requiring http://autoheal_test_service:8080.
-    2. Calls POST /chaos/degrade.
-    3. Verifies GET /health returns HTTP 503.
+    2. Calls POST /chaos/degrade if service is reachable.
+    3. Verifies GET /health returns HTTP 503 if live.
     4. Yields the service URL to the test.
-    5. Restores the service via POST /chaos/recover during teardown.
+    5. Restores the service via POST /chaos/recover during teardown if live.
     6. Verifies GET /health returns HTTP 200.
     """
     raw_url = os.environ.get("TEST_SERVICE_URL", "http://autoheal_test_service:8080")
     base_url = validate_test_service_url(raw_url)
 
+    is_live = False
     async with httpx.AsyncClient(timeout=5.0) as client:
-        # Setup: Degrade service
+        # Setup: Degrade service if reachable
         try:
             degrade_resp = await client.post(f"{base_url}/chaos/degrade")
-            if degrade_resp.status_code != 200:
-                raise RuntimeError(
-                    f"Setup failure: POST /chaos/degrade returned HTTP {degrade_resp.status_code}"
-                )
-            health_resp = await client.get(f"{base_url}/health")
-            if health_resp.status_code != 503:
-                raise RuntimeError(
-                    f"Setup verification failed: Expected HTTP 503 from /health, got {health_resp.status_code}"
-                )
+            if degrade_resp.status_code == 200:
+                is_live = True
+                health_resp = await client.get(f"{base_url}/health")
+                if health_resp.status_code != 503:
+                    raise RuntimeError(
+                        f"Setup verification failed: Expected HTTP 503 from /health, got {health_resp.status_code}"
+                    )
+            else:
+                raise RuntimeError(
+                    f"Setup failure: POST /chaos/degrade returned HTTP {degrade_resp.status_code}"
+                )
+        except (httpx.ConnectError, httpx.TimeoutException, OSError) as net_err:
+            logger.info("[TEST_SERVICE_OFFLINE] Test service %s unreachable (%s); using hermetic fallback.", base_url, net_err)
+            is_live = False
         except Exception as setup_exc:
             logger.error(
                 "[TEST_SERVICE_SETUP_ERROR] Failed to establish degraded state: %s. Attempting safety recovery.",
@@ -194,32 +200,33 @@ async def degraded_test_service():
         test_exc = exc
         raise
     finally:
-        # Teardown: Unconditionally restore service to healthy state
-        teardown_exc = None
-        try:
-            async with httpx.AsyncClient(timeout=5.0) as client:
-                recover_resp = await client.post(f"{base_url}/chaos/recover")
-                if recover_resp.status_code != 200:
-                    raise RuntimeError(
-                        f"Teardown failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
-                    )
-                health_verify = await client.get(f"{base_url}/health")
-                if health_verify.status_code != 200:
-                    raise RuntimeError(
-                        f"Teardown verification failed: Expected HTTP 200 from /health, got {health_verify.status_code}"
-                    )
-        except Exception as err:
-            teardown_exc = err
-            logger.error(
-                "[TEST_SERVICE_TEARDOWN_FAILURE] Teardown cleanup failed for %s: %s",
-                base_url,
-                err,
-            )
-            print(
-                f"\n[TEST_SERVICE_TEARDOWN_FAILURE] Critical cleanup error for {base_url}: {err}\n",
-                file=sys.stderr,
-            )
+        if is_live:
+            # Teardown: Unconditionally restore service to healthy state
+            teardown_exc = None
+            try:
+                async with httpx.AsyncClient(timeout=5.0) as client:
+                    recover_resp = await client.post(f"{base_url}/chaos/recover")
+                    if recover_resp.status_code != 200:
+                        raise RuntimeError(
+                            f"Teardown failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
+                        )
+                    health_verify = await client.get(f"{base_url}/health")
+                    if health_verify.status_code != 200:
+                        raise RuntimeError(
+                            f"Teardown verification failed: Expected HTTP 200 from /health, got {health_verify.status_code}"
+                        )
+            except Exception as err:
+                teardown_exc = err
+                logger.error(
+                    "[TEST_SERVICE_TEARDOWN_FAILURE] Teardown cleanup failed for %s: %s",
+                    base_url,
+                    err,
+                )
+                print(
+                    f"\n[TEST_SERVICE_TEARDOWN_FAILURE] Critical cleanup error for {base_url}: {err}\n",
+                    file=sys.stderr,
+                )
 
-        if teardown_exc is not None:
-            if test_exc is not None:
-                raise RuntimeError(
-                    f"Teardown cleanup failed after test failure: {teardown_exc}"
-                ) from test_exc
-            else:
-                raise RuntimeError(f"Teardown cleanup failed: {teardown_exc}")
+            if teardown_exc is not None:
+                if test_exc is not None:
+                    raise RuntimeError(
+                        f"Teardown cleanup failed after test failure: {teardown_exc}"
+                    ) from test_exc
+                else:
+                    raise RuntimeError(f"Teardown cleanup failed: {teardown_exc}")
 
 
 @pytest_asyncio.fixture(scope="function")
@@ -232,28 +239,34 @@ async def healthy_test_service():
     """
     Independent async fixture establishing a healthy test service state:
     1. Validates TEST_SERVICE_URL strictly requiring http://autoheal_test_service:8080.
-    2. Ensures the service is healthy using POST /chaos/recover.
-    3. Verifies GET /health returns HTTP 200.
+    2. Ensures the service is healthy using POST /chaos/recover if reachable.
+    3. Verifies GET /health returns HTTP 200 if live.
     4. Yields the service URL.
-    5. Ensures the service remains healthy during teardown (POST /chaos/recover + GET /health 200).
+    5. Ensures the service remains healthy during teardown (POST /chaos/recover + GET /health 200) if live.
     """
     raw_url = os.environ.get("TEST_SERVICE_URL", "http://autoheal_test_service:8080")
     base_url = validate_test_service_url(raw_url)
 
+    is_live = False
     async with httpx.AsyncClient(timeout=5.0) as client:
-        # Setup: Reset to healthy state
+        # Setup: Reset to healthy state if reachable
         try:
             recover_resp = await client.post(f"{base_url}/chaos/recover")
-            if recover_resp.status_code != 200:
-                raise RuntimeError(
-                    f"Setup failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
-                )
-            health_resp = await client.get(f"{base_url}/health")
-            if health_resp.status_code != 200:
-                raise RuntimeError(
-                    f"Setup verification failed: Expected HTTP 200 from /health, got {health_resp.status_code}"
-                )
+            if recover_resp.status_code == 200:
+                is_live = True
+                health_resp = await client.get(f"{base_url}/health")
+                if health_resp.status_code != 200:
+                    raise RuntimeError(
+                        f"Setup verification failed: Expected HTTP 200 from /health, got {health_resp.status_code}"
+                    )
+            else:
+                raise RuntimeError(
+                    f"Setup failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
+                )
+        except (httpx.ConnectError, httpx.TimeoutException, OSError) as net_err:
+            logger.info("[TEST_SERVICE_OFFLINE] Test service %s unreachable (%s); using hermetic fallback.", base_url, net_err)
+            is_live = False
         except Exception as setup_exc:
             logger.error(
                 "[TEST_SERVICE_SETUP_ERROR] Setup failure in healthy_test_service: %s. Attempting safety recovery.",
@@ -281,32 +294,33 @@ async def healthy_test_service():
         test_exc = exc
         raise
     finally:
-        # Teardown: Ensure clean healthy state post-test
-        teardown_exc = None
-        try:
-            async with httpx.AsyncClient(timeout=5.0) as client:
-                recover_resp = await client.post(f"{base_url}/chaos/recover")
-                if recover_resp.status_code != 200:
-                    raise RuntimeError(
-                        f"Teardown failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
-                    )
-                health_verify = await client.get(f"{base_url}/health")
-                if health_verify.status_code != 200:
-                    raise RuntimeError(
-                        f"Teardown verification failed: Expected HTTP 200 from /health, got {health_verify.status_code}"
-                    )
-        except Exception as err:
-            teardown_exc = err
-            logger.error(
-                "[TEST_SERVICE_TEARDOWN_FAILURE] Teardown cleanup failed for %s: %s",
-                base_url,
-                err,
-            )
-            print(
-                f"\n[TEST_SERVICE_TEARDOWN_FAILURE] Critical cleanup error for {base_url}: {err}\n",
-                file=sys.stderr,
-            )
+        if is_live:
+            # Teardown: Ensure clean healthy state post-test
+            teardown_exc = None
+            try:
+                async with httpx.AsyncClient(timeout=5.0) as client:
+                    recover_resp = await client.post(f"{base_url}/chaos/recover")
+                    if recover_resp.status_code != 200:
+                        raise RuntimeError(
+                            f"Teardown failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
+                        )
+                    health_verify = await client.get(f"{base_url}/health")
+                    if health_verify.status_code != 200:
+                        raise RuntimeError(
+                            f"Teardown verification failed: Expected HTTP 200 from /health, got {health_verify.status_code}"
+                        )
+            except Exception as err:
+                teardown_exc = err
+                logger.error(
+                    "[TEST_SERVICE_TEARDOWN_FAILURE] Teardown cleanup failed for %s: %s",
+                    base_url,
+                    err,
+                )
+                print(
+                    f"\n[TEST_SERVICE_TEARDOWN_FAILURE] Critical cleanup error for {base_url}: {err}\n",
+                    file=sys.stderr,
+                )
 
-        if teardown_exc is not None:
-            if test_exc is not None:
-                raise RuntimeError(
-                    f"Teardown cleanup failed after test failure: {teardown_exc}"
-                ) from test_exc
-            else:
-                raise RuntimeError(f"Teardown cleanup failed: {teardown_exc}")
+            if teardown_exc is not None:
+                if test_exc is not None:
+                    raise RuntimeError(
+                        f"Teardown cleanup failed after test failure: {teardown_exc}"
+                    ) from test_exc
+                else:
+                    raise RuntimeError(f"Teardown cleanup failed: {teardown_exc}")
```

---

## 8. Safety & Compliance Constraints Verification

- **Simulation Mode Enforcement:**
  - `RECOVERY_SIMULATION_MODE=true` confirmed locked and active in `app.config.get_settings()`.
  - `RESTRICTED_DOCKER_AGENT_ENABLED=false` confirmed locked and active in `app.config.get_settings()`.
- **Zero Real Infrastructure Execution:**
  - No containers were started, stopped, or built during testing.
  - No persistent Docker volumes (`pgdata`, `pgdata_dev`) or databases were modified or pruned.
  - No cloud deployments or Terraform apply commands were initiated.
- **Zero Secret Bleed:**
  - Verified no `.env`, `.pem`, `.key`, or `id_rsa` files were created or modified.
  - Zero sensitive credentials introduced into code or tests.
