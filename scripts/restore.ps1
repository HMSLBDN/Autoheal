# AutoHeal DevOps — Safe Database Restore Script (PowerShell)
param (
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,

    [Parameter(Mandatory=$true)]
    [string]$ConfirmTargetDb,

    [string]$DbUrl = "",
    [switch]$ForceProductionRestore,
    [switch]$SkipPreSnapshot
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Split-Path -Parent $ScriptDir

Write-Host "==> Initiating AutoHeal database restore..." -ForegroundColor Yellow

$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
if (!(Test-Path $PythonExe)) {
    $PythonExe = "python"
}

$ArgsList = @(
    (Join-Path $RootDir "backend\scripts\restore_db.py"),
    "--backup-file", $BackupFile,
    "--confirm-target-db", $ConfirmTargetDb
)

if ($DbUrl -ne "") {
    $ArgsList += @("--db-url", $DbUrl)
}

if ($ForceProductionRestore) {
    $ArgsList += "--force-production-restore"
}

if ($SkipPreSnapshot) {
    $ArgsList += "--skip-pre-snapshot"
}

& $PythonExe $ArgsList
if ($LASTEXITCODE -eq 0) {
    Write-Host "==> Database restore completed successfully." -ForegroundColor Green
} else {
    Write-Host "==> Database restore aborted or failed with exit code $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}
