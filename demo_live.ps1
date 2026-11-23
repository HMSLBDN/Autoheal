# AutoHeal DevOps — Live Expo Demonstration Script
# Demonstrates: Detect -> Diagnose -> Recover -> Verify
param(
    [string]$Service = "payments-api",
    [int]$Port = 8082,
    [string]$BaseApi = "http://127.0.0.1:8000"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " AutoHeal DevOps — Real-Time Self-Healing Live Demonstration" -ForegroundColor Cyan
Write-Host " Tagline: Detect. Diagnose. Recover. Verify." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Authenticate with Operator Credentials
Write-Host "`n[1/6] Authenticating operator session..." -ForegroundColor Yellow
$loginBody = @{ email = "test.operator@autoheal.dev"; password = "StrongPassword123!" } | ConvertTo-Json
$loginRes = Invoke-RestMethod -Uri "$BaseApi/api/v1/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($loginRes.access_token)" }
Write-Host "Authenticated as $($loginRes.user.full_name) (Role: $($loginRes.user.role))" -ForegroundColor Green

# 2. Trigger Controlled Failure on Sample Microservice
Write-Host "`n[2/6] Triggering controlled failure on $Service (Port $Port)..." -ForegroundColor Yellow
$chaosRes = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/chaos/fail" -Method Post
Write-Host "Chaos injected: $($chaosRes.message) (State: $($chaosRes.state.status))" -ForegroundColor Red

# 3. Detect Failure via AutoHeal Monitoring
Write-Host "`n[3/6] AutoHeal active monitoring detecting failure..." -ForegroundColor Yellow
$checkRes = Invoke-RestMethod -Uri "$BaseApi/api/v1/services/check" -Method Post -Headers $headers
$svc = Invoke-RestMethod -Uri "$BaseApi/api/v1/services/svc-payments" -Method Get -Headers $headers
Write-Host "AutoHeal detected service status: $($svc.status) (Error rate: $($svc.errorRate)%)" -ForegroundColor Red

# 4. Fetch Detected Incident & AI Diagnosis
Write-Host "`n[4/6] Inspecting generated incident & AI root-cause diagnosis..." -ForegroundColor Yellow
$incidents = Invoke-RestMethod -Uri "$BaseApi/api/v1/incidents" -Method Get -Headers $headers
$targetInc = $incidents | Where-Object { $_.serviceName -eq $Service -and $_.status -ne "resolved" } | Select-Object -First 1
Write-Host "Incident ID: $($targetInc.id)" -ForegroundColor Cyan
Write-Host "Severity:    $($targetInc.severity)" -ForegroundColor Red
Write-Host "Title:       $($targetInc.title)"
Write-Host "Cause:       $($targetInc.probableCause)" -ForegroundColor Yellow
Write-Host "Action:      $($targetInc.recommendedAction)" -ForegroundColor Cyan

# 5. Policy Approval Governance
Write-Host "`n[5/6] Operator reviewing and approving recovery action..." -ForegroundColor Yellow
$recoveries = Invoke-RestMethod -Uri "$BaseApi/api/v1/recoveries" -Method Get -Headers $headers
$targetRec = $recoveries | Where-Object { $_.incidentId -eq $targetInc.id } | Select-Object -First 1
Write-Host "Recovery action $($targetRec.id) initial status: $($targetRec.status) (Approval required: $($targetRec.approvalRequired))"

if ($targetRec.status -eq "pending_approval") {
    $approved = Invoke-RestMethod -Uri "$BaseApi/api/v1/recoveries/$($targetRec.id)/approve" -Method Post -Headers $headers
    Write-Host "Operator approved recovery action: $($approved.status)" -ForegroundColor Green
} else {
    Write-Host "Recovery action is already in state: $($targetRec.status)" -ForegroundColor Green
}

# 6. Execute Recovery & Verify Live Health
Write-Host "`n[6/6] Executing recovery action and verifying live health..." -ForegroundColor Yellow
$executed = Invoke-RestMethod -Uri "$BaseApi/api/v1/recoveries/$($targetRec.id)/execute" -Method Post -Headers $headers
Write-Host "Execution status: $($executed.status)" -ForegroundColor Green
Write-Host "Health verification: $($executed.verification)" -ForegroundColor Green
Write-Host "Execution duration: $($executed.durationSeconds)s"

# Final Verification
$finalInc = Invoke-RestMethod -Uri "$BaseApi/api/v1/incidents/$($targetInc.id)" -Method Get -Headers $headers
$finalSvc = Invoke-RestMethod -Uri "$BaseApi/api/v1/services/svc-payments" -Method Get -Headers $headers
Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " FINAL CLOSED-LOOP RESULT:" -ForegroundColor Green
Write-Host " Incident status: $($finalInc.status) ($($finalInc.recoveryStatus))" -ForegroundColor Green
Write-Host " Service health:  $($finalSvc.status) (Latency: $($finalSvc.latencyMs)ms, Error Rate: $($finalSvc.errorRate)%)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
