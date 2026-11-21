# AutoHeal DevOps — Troubleshooting & Diagnostic Guide

This guide provides diagnostic procedures and verified resolutions for common operational, development, and containerization issues in AutoHeal DevOps.

---

## 1. Windows Execution & AppLocker Issues

### Symptom: `Program 'pytest.exe' failed to run: An Application Control policy has blocked this file`
- **Cause**: Windows AppLocker or Software Restriction Policies (SRP) restrict executing standalone `.exe` binaries from user directory paths such as `.venv\Scripts\pytest.exe`, `uvicorn.exe`, or `celery.exe`.
- **Resolution**: Always invoke Python tools using the base Python interpreter with the `-m` (module) flag:
  ```powershell
  # Run pytest
  .\.venv\Scripts\python -m pytest backend/tests

  # Run uvicorn
  .\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload

  # Run celery
  .\.venv\Scripts\python -m celery -A app.worker.celery_app worker
  ```

---

## 2. Docker & Containerization Issues

### Symptom: `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`
- **Cause**: The Docker Desktop Linux VM daemon is not running, crashed, or currently initializing.
- **Resolution**:
  1. Open Docker Desktop from the Start Menu.
  2. Verify WSL2 is responsive: `wsl -l -v`.
  3. Wait until the Docker engine status icon turns green, or verify from PowerShell:
     ```powershell
     docker info
     ```
  4. If the pipe remains unavailable, restart the Docker Desktop service:
     ```powershell
     Restart-Service *docker* -ErrorAction SilentlyContinue
     ```

### Symptom: `path / is mounted on / but it is not a shared or slave mount`
- **Cause**: Occurs on Docker Desktop when a container (e.g. `node_exporter`) attempts to bind-mount the host root `/` with shared mount propagation flags on an unsupported Windows/WSL2 mount point.
- **Resolution**: In `docker-compose.yml`, mount specific system metrics partitions (e.g. `/proc`, `/sys`) in read-only mode (`:ro`) instead of recursive root bind-mounts, or ensure `rslave` propagation is supported in the Linux distribution.

---

## 3. Configuration & Startup Validation Failures

### Symptom: `ValueError: ALERTMANAGER_HMAC_SECRET is missing or using an insecure default value`
- **Cause**: In `production` or `staging` environments (`APP_ENV=production`), the application enforces strict startup validation rejecting empty or default webhook secrets (`autoheal_dev_alertmanager_webhook_secret_32chars` or legacy secrets).
- **Resolution**: Generate a strong 32-character random secret and supply it via environment variable:
  ```bash
  # Linux/macOS
  export ALERTMANAGER_HMAC_SECRET=$(openssl rand -hex 32)

  # Windows PowerShell
  $env:ALERTMANAGER_HMAC_SECRET = -join ((1..32) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })
  ```
  Ensure `ALERTMANAGER_HMAC_SECRET` is also updated in `monitoring/alertmanager.yml`.

### Symptom: `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from given URL string`
- **Cause**: `DATABASE_URL` is empty, unset, or specifies a plain `postgres://` or `postgresql://` URI without the asyncpg driver dialect required by SQLAlchemy async engine.
- **Resolution**: AutoHeal automatically normalizes URLs in `app.config.normalize_database_url`, but ensure `DATABASE_URL` is configured in your `.env` file:
  ```env
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/autoheal_db
  ```

---

## 4. Authentication & Real-Time SSE Stream Issues

### Symptom: `HTTP 401 Unauthorized` on `/api/v1/events/stream?ticket=...`
- **Cause**:
  1. **Single-Use Ticket Consumed**: SSE tickets are burned immediately upon first connection. If the browser or client attempts to reconnect using the same ticket URL, the request is rejected.
  2. **Ticket Expired**: Tickets have a strict 60-second time-to-live (`SSE_TICKET_EXPIRE_SECONDS = 60`).
- **Resolution**: The client application must request a fresh ticket via `POST /api/v1/events/ticket` before establishing or reconnecting the EventSource stream:
  ```typescript
  // Correct client reconnection pattern
  const res = await fetch('/api/v1/events/ticket', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` }
  });
  const { ticket } = await res.json();
  const es = new EventSource(`/api/v1/events/stream?ticket=${ticket}`);
  ```

---

## 5. Celery & Task Worker Issues

### Symptom: Recovery tasks hang or worker becomes unresponsive
- **Cause**: Worker reached soft/hard time limits or Redis broker connection was severed.
- **Resolution**:
  1. AutoHeal enforces bounded timeouts: `task_time_limit = 180s` (hard) and `task_soft_time_limit = 120s` (soft).
  2. Check worker liveness:
     ```powershell
     .\.venv\Scripts\python -m celery -A app.worker.celery_app inspect ping
     ```
  3. Inspect active tasks:
     ```powershell
     .\.venv\Scripts\python -m celery -A app.worker.celery_app inspect active
     ```
  4. Ensure Redis is responding:
     ```powershell
     redis-cli ping
     ```

---

## 6. Database Migration Conflicts

### Symptom: Alembic reports `Multiple head revisions are present`
- **Cause**: Concurrent branches created divergent migration files.
- **Resolution**: Merge the heads into a single revision:
  ```powershell
  $env:PYTHONPATH="backend"
  alembic -c backend/alembic.ini merge heads -m "merge_migration_heads"
  alembic -c backend/alembic.ini upgrade head
  ```
