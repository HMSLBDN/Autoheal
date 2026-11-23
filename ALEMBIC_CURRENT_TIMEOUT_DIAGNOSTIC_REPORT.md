# AutoHeal DevOps — Alembic Current Revision Check Timeout & Deadlock Diagnostic Report

**Date:** 2026-11-23  
**Repository:** https://github.com/HMSLBDN/Autoheal.git  
**Target Environment:** Unified Vercel Services (FastAPI + Next.js)  
**Production Database:** Neon PostgreSQL Serverless (`ep-cold-bird-a1f6thrt-pooler.ap-southeast-1.aws.neon.tech`)  
**Status:** **DIAGNOSTIC COMPLETE & ROOT CAUSES RESOLVED**

---

## 1. Problem Description

During execution of `migrate_production.ps1`, the script succeeded at step `[1/5]` (URL parsing and Neon host validation) but hung indefinitely at step `[2/5]`:

```text
[2/5] Checking current Alembic revision in database...
(Hangs indefinitely with no CPU activity, no error output, and no timeout)
```

Target parameters confirmed:
- **Host:** `ep-cold-bird-a1f6thrt-pooler.ap-southeast-1.aws.neon.tech`
- **Database:** `neondb`
- **Driver:** `postgresql+asyncpg`
- **TLS:** Encrypted

---

## 2. Root Cause Analysis

Four distinct technical factors contributed to the hang:

### Root Cause 1: Synchronous Stream Read Deadlock in `Invoke-ProcessCapture`
In `migrate_production.ps1`:
```powershell
$p = [System.Diagnostics.Process]::Start($pinfo)
$stdout = $p.StandardOutput.ReadToEnd()
$stderr = $p.StandardError.ReadToEnd()
$p.WaitForExit()
```
- **The Deadlock:** `StandardOutput.ReadToEnd()` runs synchronously on the main thread before `StandardError.ReadToEnd()`. When Alembic starts up, it logs informational messages or connection retry notices to `stderr` (e.g. `INFO [alembic.runtime.migration] Context impl PostgresqlImpl`).
- On Windows, anonymous pipes have a fixed 4,096-byte OS buffer. If the child process emits tracebacks, warnings, or logs that exceed 4KB to `stderr`, the child process blocks waiting for the pipe buffer to drain. Meanwhile, the PowerShell parent process is blocked waiting for EOF on `stdout`.
- Neither process can make forward progress, resulting in a **permanent mutual deadlock**.
- **No Timeout:** `WaitForExit()` had no timeout argument. Even without buffer exhaustion, any network latency, cold compute wake-up, or socket stall blocked the process indefinitely.

### Root Cause 2: Neon Pooled Endpoint (`-pooler`) vs. Direct Migration Connections
The connection string used points to:
`ep-cold-bird-a1f6thrt-pooler.ap-southeast-1.aws.neon.tech`
- The `-pooler` suffix directs connections through **PgBouncer in transaction pooling mode**.
- In transaction pooling mode, prepared statements are disabled, session variables are not preserved across queries, and advisory locks/DDL transactions can stall or fail.
- **Neon Official Architectural Guidance:** Neon explicitly advises using the **direct connection string** (without `-pooler`) for Alembic and DDL migrations:
  - **Direct Endpoint:** `ep-cold-bird-a1f6thrt.ap-southeast-1.aws.neon.tech`
  - **Pooled Endpoint:** `ep-cold-bird-a1f6thrt-pooler.ap-southeast-1.aws.neon.tech` (optimized for ephemeral HTTP serverless requests in runtime, not migration DDL)
- Furthermore, `asyncpg` enables prepared statement caching by default. When connecting through a transaction pooler, prepared statement caching can cause queries to fail or hang unless `statement_cache_size=0` is configured.

### Root Cause 3: Asyncpg Connection Timeout & Python 3.12 String Query Pitfall
- In `asyncpg`, if no connection timeout is configured, socket connection attempts rely on the OS TCP handshake timeout (which can take 2 minutes or longer on Windows before failing).
- When attempting to pass `timeout` or `command_timeout` in the SQLAlchemy URL query string (e.g. `?timeout=30`), SQLAlchemy forwards query parameters to `asyncpg.connect()` as **strings** (`timeout='30'`).
- In Python 3.12, `asyncio.timeouts.timeout(delay)` computes `loop.time() + delay`. When `delay` is a string, Python immediately raises:
  `TypeError: unsupported operand type(s) for +: 'float' and 'str'`
- Therefore, connection timeouts must be explicitly typed as `float` numbers and passed via `connect_args["timeout"] = 30.0`, rather than left in the URL query string.

### Root Cause 4: Alembic `env.py` Engine Configuration Gap
In `backend/alembic/env.py`:
- `prepare_database_url_and_args(raw_db_url)` was called, but the second return value (`extra_args`, which contains `connect_args`) was discarded with `_`.
- As a result, Alembic's `async_engine_from_config` did not inherit `server_settings`, `statement_cache_size=0`, or `timeout=30.0`.

---

## 3. Implemented Solutions

### 1. Deadlock-Free Asynchronous Stream Capture with 45s Timeout
Updated `Invoke-ProcessCapture` in [migrate_production.ps1](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/migrate_production.ps1):
- Attached `Register-ObjectEvent` handlers to `OutputDataReceived` and `ErrorDataReceived` with background `StringBuilder` buffers.
- Enabled `BeginOutputReadLine()` and `BeginErrorReadLine()` so both streams drain concurrently in real time, preventing pipe buffer deadlocks.
- Configured a 45-second timeout (`$p.WaitForExit($timeoutMs)`).
- On timeout, the child process is safely terminated via `$p.Kill()`, preventing orphaned processes.
- Returns structured object with `TimedOut = $true`, `ExitCode = -1`, and descriptive error text.

### 2. Guard Against Mistaking Timeout for an Empty Database
Updated Step `[2/5]` in [migrate_production.ps1](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/migrate_production.ps1):
- Explicitly checks `if ($currentRes.TimedOut)` and prints detailed diagnostic guidance (Neon cold start, direct vs pooled connection, firewall port 5432).
- Explicitly checks `if ($currentRes.ExitCode -ne 0)` and displays stderr details.
- Only treats revision as empty if `ExitCode -eq 0`, `TimedOut -eq $false`, and `StdOut` is genuinely blank.

### 3. Automatic Detection of Pooled Endpoints & Direct Fallback Guidance
In [migrate_production.ps1](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/migrate_production.ps1):
- Automatically detects `-pooler` in `$targetHost`.
- Displays notice that `statement_cache_size=0` is active.
- Computes `$directHost = $targetHost.Replace("-pooler", "")` and displays a direct tip to the user.

### 4. Typed Asyncpg Connection Arguments in `database.py`
Updated `prepare_database_url_and_args` in [backend/app/database.py](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/backend/app/database.py):
- Extracts `timeout` and `command_timeout` from URL query, parses them as typed `float` values (defaulting to `30.0` seconds), and places them in `connect_args`.
- Automatically sets `connect_args["statement_cache_size"] = 0` when connecting to `-pooler` hosts.
- Strips non-safe parameters from the URL query, avoiding the Python 3.12 `TypeError`.

### 5. Propagated Engine Arguments to Alembic
Updated [backend/alembic/env.py](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/backend/alembic/env.py):
- Captures `extra_args` from `prepare_database_url_and_args`.
- Forwards `connect_args` (including `server_settings`, `statement_cache_size=0`, and `timeout=30.0`) directly into `async_engine_from_config`.

---

## 4. Verification & Validation Evidence

1. **PowerShell 5.1 AST Syntax Parsing:**
   ```powershell
   powershell.exe -NoProfile -Command '$pErrors = $null; $ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\migrate_production.ps1).Path, [ref]$null, [ref]$pErrors); Write-Host "ErrorCount: $($pErrors.Count)"'
   # ErrorCount: 0
   # SUCCESS: 0 syntax errors in Windows PowerShell 5.1
   ```
2. **Buffer Overflow & Timeout Killing Verification:**
   - Tested capturing 100,000 bytes on both stdout and stderr simultaneously: completed in under 1 second with 0 deadlocks.
   - Tested 10-second sleep process with 2-second timeout: process safely killed, exit code `-1`, `TimedOut: True`.
3. **Asyncpg Connection Timeout Verification:**
   - Verified that `create_async_engine(..., connect_args={'timeout': 2.0})` against an unreachable IP cleanly triggers `TimeoutError` in exactly 2.05s without hanging.
4. **Pytest Normalization Suite:**
   - Executed `pytest backend/tests/test_database_url_normalization.py`: **13 passed**.
5. **Alembic Discovery:**
   - `python -m alembic -c backend/alembic.ini heads` -> `0010_add_phase16_recovery_classification (head)`.
6. **Git Diff Check:**
   - `git diff --check` passed with 0 errors.

---

## 5. Production Recommendations for Migration Execution

When running the migration:

1. **Recommended Connection String:**
   Use the **direct** Neon connection string (without `-pooler`):
   ```text
   postgresql://<user>:<password>@ep-cold-bird-a1f6thrt.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
   *(Notice: `ep-cold-bird-a1f6thrt` instead of `ep-cold-bird-a1f6thrt-pooler`)*
2. **Neon Compute Wake-up:**
   If the compute endpoint is sleeping, the first connection may take 5–10 seconds to spin up. The runner now allows 45 seconds before timing out.
3. **Execution Command:**
   In your integrated terminal:
   ```powershell
   .\migrate_production.ps1
   ```
