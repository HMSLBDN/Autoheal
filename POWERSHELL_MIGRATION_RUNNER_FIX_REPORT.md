# AutoHeal DevOps — PowerShell Migration Runner Fix Report

**Date:** November 23, 2026  
**Repository:** `https://github.com/HMSLBDN/Autoheal.git`  
**Target:** `migrate_production.ps1`  
**Configuration File:** `backend/alembic.ini`  
**Platform:** Windows PowerShell 5.1 / PowerShell Core  
**Safety Status:** `RECOVERY_SIMULATION_MODE=True`, `RESTRICTED_DOCKER_AGENT_ENABLED=False`  

---

## 1. Problem Analysis & Root Cause

During the previous execution attempt of `migrate_production.ps1`, the script failed during the pre-migration `alembic current` check with:
```text
At migrate_production.ps1 line 91:
$currentOutput = & $pyExe -m alembic -c $iniPath current 2>&1
PowerShell reported NativeCommandError / RemoteException.
The Alembic output:
0010_add_phase16_recovery_classification (head)
was subsequently interpreted as a PowerShell command.
```

### Detailed Technical Explanation:
1. **Windows PowerShell 5.1 `NativeCommandError` Behavior:**
   * At the top of `migrate_production.ps1`, `$ErrorActionPreference = "Stop"` was configured.
   * In Windows PowerShell 5.1, when an external executable emits data to standard error (`stderr`), and standard error is merged using the `2>&1` redirection operator, PowerShell wraps every line of stderr into a `[System.Management.Automation.ErrorRecord]`.
   * With `$ErrorActionPreference = "Stop"`, PowerShell treats this `ErrorRecord` as a fatal terminating exception (`NativeCommandError`), even when the process exits with status code `0`.
   * Alembic and Python standard logging write informational messages (e.g. `INFO [alembic.runtime.migration] Context impl AsyncpgImpl.`) to `stderr` by default (as configured in `backend/alembic.ini`: `StreamHandler(sys.stderr)`).
   * Consequently, PowerShell aborted on normal informational logging before inspecting the exit code or capturing stdout.
2. **Command Pipeline Evaluation of `(head)`:**
   * When standard error triggered `NativeCommandError`, the remaining uncaptured stdout stream containing `0010_add_phase16_recovery_classification (head)` was emitted onto the PowerShell host console/pipeline.
   * In PowerShell, unquoted tokens containing parentheses (e.g. `(head)`) are parsed as command invocations or subexpressions. PowerShell attempted to resolve `0010_add_phase16_recovery_classification` as a cmdlet/function, producing a command-not-found error.
3. **Empty Database Handling:**
   * On an uninitialized database (where `alembic_version` has no records or does not exist), Alembic outputs an empty string to stdout with exit code `0`.
   * The previous script lacked clear differentiation between an empty database (success with no revisions) and a network/credential error (exit code `1` with error message).

---

## 2. Implemented Architecture Fixes in `migrate_production.ps1`

### 1. `Invoke-ProcessCapture` (Clean StdOut/StdErr Isolation)
To capture output without triggering `NativeCommandError` or evaluating text in the PowerShell pipeline, we implemented a dedicated process runner using .NET `System.Diagnostics.Process`:
```powershell
function Invoke-ProcessCapture {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$ArgumentList
    )

    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $FilePath
    $pinfo.Arguments = ($ArgumentList -join " ")
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $p = [System.Diagnostics.Process]::Start($pinfo)
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $p.WaitForExit()

    return [PSCustomObject]@{
        ExitCode = $p.ExitCode
        StdOut   = $stdout
        StdErr   = $stderr
    }
}
```
* **No `2>&1` Redirection:** Stdout and stderr are read cleanly through .NET streams into string properties.
* **No NativeCommandError:** Logging to stderr does not trigger PowerShell exceptions.
* **Exact Exit Codes:** Directly returns `$p.ExitCode`.

### 2. `Invoke-ProcessLive` (Interactive Console Streaming for `upgrade head`)
During the actual migration execution, we stream logs to the console in real time while scoping `$ErrorActionPreference`:
```powershell
function Invoke-ProcessLive {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$ArgumentList
    )

    $savedEAP = $global:ErrorActionPreference
    $global:ErrorActionPreference = "Continue"
    try {
        & $FilePath $ArgumentList
        $nativeCode = $LASTEXITCODE
        return $nativeCode
    } finally {
        $global:ErrorActionPreference = $savedEAP
    }
}
```

### 3. Clear Revision & Error Classification
* **Pre-check inspection logic:**
  ```powershell
  if ($currentRes.ExitCode -ne 0) {
      Write-Host "[ERROR] Failed to query current revision. Database connection failed!" -ForegroundColor Red
      # Display stderr details, clean up memory, and abort immediately
      exit 1
  }

  $currentRaw = $currentRes.StdOut.Trim()
  if (-not $currentRaw) {
      $prevRevision = "None (empty / uninitialized database)"
      Write-Host "  Current state: Fresh database detected (no existing revisions applied)." -ForegroundColor Cyan
  } else {
      $prevRevision = $currentRaw
      Write-Host "  Current revision: $prevRevision" -ForegroundColor Cyan
  }
  ```
* Genuinely failed connections (exit code `1`) halt execution immediately and never proceed to `upgrade head`.
* Fresh databases (exit code `0` with empty stdout) proceed safely to `upgrade head`.

### 4. Preservation of Security & Configuration Guarantees
* **Alembic Path:** Anchored to `$backendDir\alembic.ini` using `script_location = %(here)s/alembic`.
* **Credential Masking:** Input collected via `Read-Host -AsSecureString` (never saved to disk or logged).
* **Host Guard:** Validates host ends in `.neon.tech`.
* **Table Verification:** Connects via asyncpg and verifies all 43 tables (including `users` and `organizations`).
* **Memory Cleanup:** Deletes `$env:DATABASE_URL` and runs garbage collection.

---

## 3. Validation & Testing Results

1. **Alembic Heads Discovery:**
   * Command: `python -m alembic -c backend/alembic.ini heads`
   * Result: `0010_add_phase16_recovery_classification (head)`
   * Exit Code: `0`
2. **Alembic History Discovery:**
   * Command: `python -m alembic -c backend/alembic.ini history`
   * Result: Full 10-revision linear chain resolved (`<base>` -> `0001` -> ... -> `0010`).
   * Exit Code: `0`
3. **Empty Database Handling Test:**
   * Simulated empty stdout with exit code `0` and stderr info logging.
   * Result: Accurately recognized as `None (empty / uninitialized database)` without errors.
4. **Error Handling Test:**
   * Simulated failure with exit code `1` and stderr traceback.
   * Result: Accurately caught non-zero exit code, extracted error message, and aborted cleanly.
5. **PowerShell 5.1 Script Syntax:**
   * `[System.Management.Automation.Language.Parser]::ParseFile` -> `Syntax OK`.
6. **Git Formatting:**
   * `git diff --check` -> `0 errors`.

---

## 4. Current Status

* **Status:** **REPAIRED AND VALIDATED**
* **Safety Pause:** In accordance with instructions, `upgrade head` has **NOT** been executed.
* **Next Action:** You can now run `.\migrate_production.ps1` in your integrated terminal.
