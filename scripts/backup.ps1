# AutoHeal DevOps — Database Backup Script (PowerShell)
param (
    [string]$OutputDir = "./backups",
    [int]$RetentionDays = 7,
    [string]$DbUrl = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Split-Path -Parent $ScriptDir

Write-Host "==> Starting AutoHeal database backup..." -ForegroundColor Cyan

$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
if (!(Test-Path $PythonExe)) {
    $PythonExe = "python"
}

$ArgsList = @(
    (Join-Path $RootDir "backend\scripts\backup_db.py"),
    "--output-dir", $OutputDir,
    "--retention-days", $RetentionDays
)

if ($DbUrl -ne "") {
    $ArgsList += @("--db-url", $DbUrl)
}

if ($DryRun) {
    $ArgsList += "--dry-run"
}

& $PythonExe $ArgsList
if ($LASTEXITCODE -eq 0) {
    Write-Host "==> Backup completed successfully." -ForegroundColor Green
} else {
    Write-Host "==> Backup failed with exit code $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}
