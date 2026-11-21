# AutoHeal DevOps — Repeatable Demonstration Guide

This guide provides end-to-end Windows PowerShell instructions for running and verifying the complete AutoHeal DevOps self-healing demonstration lifecycle.

---

## 1. Prerequisites

Before running the demo, ensure the following tools are installed:
- **Operating System**: Windows 10/11 (64-bit) with PowerShell 5.1+ or PowerShell 7+
- **Docker Desktop**: Docker Engine 24+ with Compose v2
- **Python**: Python 3.11 or 3.12 (with virtual environment support)
- **Node.js**: Node.js 18+ or 20+ (for Next.js frontend if running locally outside Docker)

---

## 2. Infrastructure Setup & Container Health

Start the complete AutoHeal multi-container stack in development mode:

```powershell
# 1. Start all core services, telemetry pipelines, and sample microservices
docker compose -f docker-compose.dev.yml up -d

# 2. Verify container operational status and port bindings
docker compose -f docker-compose.dev.yml ps
```

### Verified Service Ports
| Container Name | Service | Local URL / Port |
| :--- | :--- | :--- |
| `autoheal_backend_dev` | FastAPI Backend | `http://localhost:8000` |
| `autoheal_test_checkout_api` | Test Microservice 1 | `http://localhost:8080` |
| `autoheal_test_customer_web` | Test Microservice 2 | `http://localhost:8081` |
| `autoheal_test_payments_api` | Test Microservice 3 | `http://localhost:8082` |
| `autoheal_prometheus_dev` | Prometheus Monitoring | `http://localhost:9090` |
| `autoheal_alertmanager_dev` | Alertmanager Ingestion | `http://localhost:9093` |
| `autoheal_grafana_dev` | Grafana Dashboards | `http://localhost:3001` |
| `autoheal_db_dev` | PostgreSQL Database | `localhost:5432` |
| `autoheal_redis_dev` | Redis Broker & Cache | `localhost:6379` |

### Health Check Command
```powershell
# Query backend readiness and dependency health
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -Method Get | ConvertTo-Json
```

---

## 3. User Registration & Operator Authentication

### Option A: Using the Web Interface
1. Open your browser and navigate to `http://localhost:3000/register`.
2. Register a new user with an **Operator** or **Admin** role.
3. Sign in at `http://localhost:3000/login` to access the dashboard.

### Option B: Using PowerShell (Headless API)
```powershell
# 1. Register an Operator user
$regBody = @{
    email = "operator@autoheal.local"
    password = "SecurePassword123!"
    full_name = "Lead DevOps Operator"
    role = "operator"
    organization_name = "Acme Cloud Workspace"
} | ConvertTo-Json

$registerResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/register" -Method Post -Body $regBody -ContentType "application/json"
$token = $registerResponse.access_token

# 2. Store authentication header for subsequent API calls
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

Write-Host "Authenticated successfully as Operator. Token acquired."
```

---

## 4. Inspecting Monitored Services & Healthy Baseline

Query monitored services to confirm normal SLA parameters (0% error rate, low latency, 99.9%+ availability):

```powershell
# Inspect monitored services in the organization
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/services" -Method Get -Headers $headers | ConvertTo-Json -Depth 3
```

Check the demo environment status:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/demo/status" -Method Get -Headers $headers | ConvertTo-Json -Depth 3
```

---

## 5. Controlled Fault Injection

Simulate a production incident on `checkout-api` by injecting a controlled 5xx error spike:

```powershell
$faultPayload = @{
    service_name = "checkout-api"
    fault_type = "http_500"
    error_rate = 0.25
    latency_ms = 450
} | ConvertTo-Json

$faultResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/demo/fault" -Method Post -Headers $headers -Body $faultPayload
$faultResult | ConvertTo-Json
```

*Expected Result:*
- Microservice `checkout-api` enters `critical` state.
- Error rate spikes to 25.0%.
- Real-time Server-Sent Event (SSE) broadcasts updated telemetry to connected dashboard views.
- Audit log records `demo_fault_triggered`.

---

## 6. Alert Ingestion & Automated Incident Creation

In a live Docker setup, Prometheus scrapes `checkout-api:8080/metrics` every 15 seconds. Once the error rate threshold is breached for 30 seconds, Alertmanager sends an authenticated webhook to FastAPI (`/api/v1/alerts/webhook`).

To trigger immediate, deterministic incident creation:

```powershell
$alertPayload = @{
    service_name = "checkout-api"
    alertname = "HighErrorRate"
    severity = "critical"
    summary = "5xx HTTP error rate spike on checkout-api"
    description = "P99 error rate reached 25.0%, exceeding the 1.0% SLA threshold."
    auto_request_recovery = $true
} | ConvertTo-Json

$incidentResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/demo/simulate-alert" -Method Post -Headers $headers -Body $alertPayload
$incidentResult | ConvertTo-Json

$incidentId = $incidentResult.incident_id
$recoveryId = $incidentResult.recovery_id
Write-Host "Incident Created: $incidentId | Recovery Action Enqueued: $recoveryId"
```

---

## 7. Inspecting Incident Details & AI Root-Cause Diagnosis

Fetch the detected incident details, correlated evidence, and AI diagnosis:

```powershell
$incidentDetails = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/incidents/$incidentId" -Method Get -Headers $headers
$incidentDetails | ConvertTo-Json -Depth 4
```

*Verification Points:*
- **Probable Root Cause**: Displays root-cause diagnosis.
- **Recommended Action**: Enforces approved allowlist (`restart_service`, `clear_cache`, `scale_service`, `restore_health`, `rollback_release`).
- **Evidence Attached**: Correlated metric timestamps and diagnostic logs.

---

## 8. Human-in-the-Loop Recovery Approval

All disruptive actions require explicit authorization by an authorized Operator or Admin:

```powershell
# 1. View pending recovery action
$recoveries = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/recoveries?status=pending_approval" -Method Get -Headers $headers
$recoveries | ConvertTo-Json

# 2. Approve the recovery action
$approvalResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/recoveries/$recoveryId/approve" -Method Post -Headers $headers
$approvalResponse | ConvertTo-Json
```

*Security Check:* If a user with role `viewer` attempts approval, the backend rejects it with `403 Forbidden` (`Insufficient permissions`).

---

## 9. Simulated Recovery Execution & Post-Recovery Health Verification

Execute the approved recovery action. The recovery engine coordinates with the safe infrastructure agent adapter (`RECOVERY_SIMULATION_MODE=true`):

```powershell
# Execute recovery action
$executionResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/recoveries/$recoveryId/execute" -Method Post -Headers $headers
$executionResponse | ConvertTo-Json -Depth 3
```

*Automated Workflow Executed:*
1. State transitions: `approved` $\to$ `running` $\to$ `completed`.
2. Action executed through restricted agent adapter.
3. Post-recovery health verifier evaluates service telemetry against SLA thresholds.
4. Telemetry verified healthy:
   - Service status restored to `healthy` (error rate < 0.05%, latency < 50ms).
   - Recovery action verification marked `passed`.
   - Incident automatically marked `resolved` with `resolved_at` timestamp.
   - Audit trail records: `recovery_executed` and `recovery_verified`.

---

## 10. Downloading Incident Post-Mortem Report (PDF)

Download the official binary PDF incident report containing all telemetry, evidence, diagnosis, approval stamps, and execution receipts:

```powershell
$reportUri = "http://localhost:8000/api/v1/incidents/$incidentId/report?format=pdf"
$outputPath = "$PSScriptRoot\${incidentId}_PostMortem_Report.pdf"

Invoke-WebRequest -Uri $reportUri -Headers $headers -OutFile $outputPath
Write-Host "Post-mortem PDF report successfully saved to: $outputPath"
```

---

## 11. Reviewing Reliability Analytics & MTTR Metrics

View aggregated reliability statistics and measured response latencies:

```powershell
$analytics = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/analytics/summary" -Method Get -Headers $headers
$analytics | ConvertTo-Json
```

*Computed Metrics:*
- `detectionLatencySeconds`: Time from fault trigger to incident creation.
- `recoveryDurationMinutes`: Execution duration.
- `recoverySuccessRate`: Success percentage of terminal recoveries.
- `falsePositiveRate`: Percentage of rejected or false alarms.
- `availability`: Organization-wide service uptime percentage.

---

## 12. Resetting the Demo Environment

Restore all microservices and database states to healthy baselines:

```powershell
# Reset all monitored services
$resetResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/demo/reset" -Method Post -Headers $headers -Body "{}"
$resetResult | ConvertTo-Json
```

---

## 13. Running Automated Repeatable Experiments

To execute 5 automated empirical trials measuring statistical detection latency, MTTR, and outage reduction:

```powershell
$env:PYTHONPATH = "backend"
python scripts/run_experiments.py
```

Results are saved to `monitoring/experiment_results.json`.

---

## 14. Troubleshooting Common Issues

### 1. `403 Forbidden: Demo controls and fault injection are disabled`
- Ensure `DEMO_MODE_ENABLED=true` is set in your `.env` or environment.
- Confirm your user account has `operator` or `admin` role.

### 2. Microservice connection timeout during fault injection
- If running outside Docker, the demo router automatically simulates telemetry degradations directly in the PostgreSQL database, ensuring all workflows succeed even without Docker Desktop active.

### 3. Missing approval error (`400 Bad Request`)
- The policy engine prevents manual execution of actions requiring approval without calling `/api/v1/recoveries/{id}/approve` first.

### 4. Port Conflict on `8000` or `3000`
- Identify conflicting processes: `Get-NetTCPConnection -LocalPort 8000`
- Terminate process or re-map host port in `docker-compose.dev.yml`.
