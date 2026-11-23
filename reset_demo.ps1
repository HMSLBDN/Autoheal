# AutoHeal DevOps — Safe Demo Reset Script
param(
    [int]$Port = 8082,
    [string]$BaseApi = "http://127.0.0.1:8000"
)

Write-Host "Resetting AutoHeal live demonstration environment..." -ForegroundColor Yellow

# 1. Reset microservice directly
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/chaos/recover" -Method Post
    Write-Host "Sample microservice restored on port $($Port): $($res.message)" -ForegroundColor Green
} catch {
    Write-Host "Sample microservice was not reachable on port $Port." -ForegroundColor DarkGray
}

# 2. Reset backend demo environment
try {
    $loginBody = @{ email = "test.operator@autoheal.dev"; password = "StrongPassword123!" } | ConvertTo-Json
    $loginRes = Invoke-RestMethod -Uri "$BaseApi/api/v1/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
    $headers = @{ Authorization = "Bearer $($loginRes.access_token)" }
    $resetRes = Invoke-RestMethod -Uri "$BaseApi/api/v1/demo/reset" -Method Post -Headers $headers -ContentType "application/json" -Body "{}"
    Write-Host "AutoHeal backend reset completed: $($resetRes.message)" -ForegroundColor Green
} catch {
    Write-Host "Could not reset AutoHeal backend: $($_.Exception.Message)" -ForegroundColor Red
}
