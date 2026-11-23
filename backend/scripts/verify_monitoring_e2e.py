import httpx
import time

client = httpx.Client(base_url="http://127.0.0.1:8000")

# 1. Login
r = client.post("/api/v1/auth/login", json={"email": "test.operator@autoheal.dev", "password": "StrongPassword123!"})
token = r.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}
print("[1] Operator authenticated")

# 2. Reset to clean baseline
reset_res = client.post("/api/v1/demo/reset", headers=headers, json={})
print(f"[2] Demo reset: {reset_res.json().get('message')}")

# 3. Check baseline status of payments-api
services = client.get("/api/v1/services", headers=headers).json()
p_svc = next((s for s in services if s["name"] == "payments-api"), None)
print(f"[3] Baseline payments-api status: {p_svc['status']} (errorRate={p_svc['errorRate']}%, avail={p_svc['availability']}%)")
assert p_svc["status"] == "healthy", f"Expected healthy, got {p_svc['status']}"

# 4. Inject chaos failure into microservice
chaos_res = httpx.post("http://127.0.0.1:8082/chaos/fail")
print(f"[4] Injected chaos: {chaos_res.status_code} {chaos_res.text}")

# 5. Check microservice direct health endpoint
ms_health = httpx.get("http://127.0.0.1:8082/health")
print(f"[5] Microservice /health: HTTP {ms_health.status_code} -> {ms_health.text}")
assert ms_health.status_code == 503, "Microservice must return HTTP 503"

# 6. Wait for backend background monitoring cycle to detect failure
print("[6] Waiting for background monitoring cycle to detect failure...")
for attempt in range(12):
    time.sleep(1)
    services = client.get("/api/v1/services", headers=headers).json()
    p_svc = next((s for s in services if s["name"] == "payments-api"), None)
    if p_svc and p_svc["status"] == "critical":
        print(f"    Detected CRITICAL state on attempt {attempt+1} ({p_svc['lastChecked']})")
        break
else:
    raise AssertionError(f"Monitoring cycle did not detect critical state within 12 seconds: {p_svc}")

# 7. Check backend services endpoint
print(f"[7] Confirmed payments-api status: {p_svc['status']} (errorRate={p_svc['errorRate']}%, avail={p_svc['availability']}%, lastChecked={p_svc['lastChecked']})")
assert p_svc["status"] == "critical", f"Expected critical, got {p_svc['status']}"

# 8. Check incident created
incidents = client.get("/api/v1/incidents", headers=headers).json()
active_inc = next((i for i in incidents if i["serviceName"] == "payments-api" and i["status"] in ("open", "recovering")), None)
print(f"[8] Created incident: {active_inc['id']} | Status: {active_inc['status']} | Severity: {active_inc['severity']} | Title: {active_inc['title']}")
assert active_inc is not None, "Active incident must exist for payments-api"

# 9. Verify incident details and evidence
inc_detail = client.get(f"/api/v1/incidents/{active_inc['id']}", headers=headers).json()
print(f"[9] Incident Evidence Count: {len(inc_detail.get('evidence', []))}")
for ev in inc_detail.get("evidence", []):
    print(f"     - [{ev['kind']}] {ev['title']}: {ev['detail']}")

# 10. Verify deduplication - wait another 4 seconds and check incident count
time.sleep(4)
incidents_after = client.get("/api/v1/incidents", headers=headers).json()
active_inc_after = [i for i in incidents_after if i["serviceName"] == "payments-api" and i["status"] in ("open", "recovering")]
print(f"[10] Active incident count for payments-api after second cycle: {len(active_inc_after)} (deduplication confirmed)")
assert len(active_inc_after) == 1, "Must have exactly 1 active incident"

# 11. Restore health
recover_res = httpx.post("http://127.0.0.1:8082/chaos/recover")
print(f"[11] Injected recovery: {recover_res.status_code} {recover_res.text}")
for attempt in range(12):
    time.sleep(1)
    services = client.get("/api/v1/services", headers=headers).json()
    p_svc = next((s for s in services if s["name"] == "payments-api"), None)
    if p_svc and p_svc["status"] == "healthy":
        print(f"    Detected HEALTHY state on attempt {attempt+1}")
        break
else:
    raise AssertionError(f"Monitoring cycle did not detect healthy recovery within 12 seconds: {p_svc}")

print(f"[11b] Post-recovery payments-api status: {p_svc['status']} (errorRate={p_svc['errorRate']}%, avail={p_svc['availability']}%)")
assert p_svc["status"] == "healthy", f"Expected healthy, got {p_svc['status']}"

print("\nALL 11 VERIFICATION CHECKS PASSED PERFECTLY!")
