import httpx
import json

client = httpx.Client(base_url="http://127.0.0.1:8000")

# 1. Health
h = client.get("/api/v1/health")
assert h.status_code == 200, f"Health failed: {h.text}"
print("[PASS] 1. Backend API connected and responding:", h.json().get("status"))

# 2. Login
login = client.post("/api/v1/auth/login", json={"email": "test.operator@autoheal.dev", "password": "StrongPassword123!"})
assert login.status_code == 200, f"Login failed: {login.text}"
token = login.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}
print("[PASS] 2. Login and authentication work for operator:", login.json().get("user", {}).get("full_name"))

# 3. Services
services = client.get("/api/v1/services", headers=headers)
assert services.status_code == 200 and len(services.json()) > 0
print(f"[PASS] 3. Dashboard services inventory loaded: {len(services.json())} services")

# 4. Incidents
incidents = client.get("/api/v1/incidents", headers=headers)
assert incidents.status_code == 200
inc_list = incidents.json()
print(f"[PASS] 4. Incident detection & list loaded: {len(inc_list)} incidents")

# 5. Incident detail with evidence & diagnosis
if inc_list:
    target_id = inc_list[0]["id"]
    first_inc = client.get(f"/api/v1/incidents/{target_id}", headers=headers)
    assert first_inc.status_code == 200
    evidence = first_inc.json().get("evidence", [])
    events = first_inc.json().get("events", [])
    print(f"[PASS] 5. Incident {target_id} detail: {len(evidence)} evidence items, {len(events)} events")

# 6. Recoveries
recoveries = client.get("/api/v1/recoveries", headers=headers)
assert recoveries.status_code == 200
rec_list = recoveries.json()
print(f"[PASS] 6. Recovery queue & history loaded: {len(rec_list)} records")

# 7. Analytics
analytics = client.get("/api/v1/analytics/summary", headers=headers)
assert analytics.status_code == 200
print(f"[PASS] 7. Analytics loaded: MTTR={analytics.json().get('mttrSeconds')}s, Availability={analytics.json().get('fleetAvailability')}%")

# 8. Report downloads
if inc_list:
    pdf_rep = client.get(f"/api/v1/incidents/{target_id}/report?format=pdf", headers=headers)
    assert pdf_rep.status_code == 200 and len(pdf_rep.content) > 0
    json_rep = client.get(f"/api/v1/incidents/{target_id}/report?format=json", headers=headers)
    assert json_rep.status_code == 200 and len(json_rep.content) > 0
    print(f"[PASS] 8. Incident reports download verified (PDF: {len(pdf_rep.content)} bytes, JSON: {len(json_rep.content)} bytes)")

# 9. Frontend page responsiveness
fe = httpx.get("http://localhost:3000")
assert fe.status_code == 200
print("[PASS] 9. Frontend responds with HTTP 200 at http://localhost:3000")

print("\nALL 9 PHASE 1 FUNCTIONAL CHECKS PASSED PERFECTLY!")
