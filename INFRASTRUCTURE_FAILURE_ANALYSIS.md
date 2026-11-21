# Infrastructure Failure Analysis & Root Cause Remediation

**Phase:** 12.2 Infrastructure Activation  
**Scope:** Host Execution Constraints, Container Gaps & Resolution Analysis  
**Status:** **ALL ISSUES DIAGNOSED & FULLY RESOLVED**  

---

## 1. Issue 1: Windows Named Pipe Daemon Session Boundary

### Symptom:
Docker CLI returned: `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`

### Root Cause:
On Windows 11 with WSL2, `Docker Desktop.exe` is a user-mode interactive Windows application. Its background service bridge (`com.docker.backend.exe`) and named pipe `\\.\pipe\dockerDesktopLinuxEngine` are only initialized when the application is launched within an active interactive desktop GUI session. Subprocesses spawned from non-interactive shells cannot acquire the desktop session token.

### Resolution:
User launched Docker Desktop from Windows Start menu. The daemon acquired the GUI session handle, initialized the `docker-desktop` WSL2 VM, and exposed the named pipe. All subsequent CLI commands (`docker version`, `docker info`, `docker compose`) executed with exit code 0.

---

## 2. Issue 2: Missing OpenTelemetry Library in Stale Container Image

### Symptom:
`autoheal_backend_dev` container failed health checks with:
`ModuleNotFoundError: No module named 'opentelemetry'`

### Root Cause:
The development image `autoheal-backend:dev` was built earlier before `opentelemetry-api`, `opentelemetry-sdk`, and `opentelemetry-exporter-otlp` were added to `backend/requirements.txt` in commit `fbba276`. Because `./backend` is mounted into the container as a live volume, the newer application code ran against the older container environment.

### Resolution:
Executed `docker compose -f docker-compose.dev.yml build backend celery_worker celery_beat` to rebuild images with updated wheel dependencies. Existing database and Redis volumes (`pgdata_dev`, `redisdata_dev`) were completely preserved without modification. Recreated containers started and reached `healthy` status immediately.

---

## 3. Issue 3: Alembic Version Number Length Limit (32 Characters)

### Symptom:
Alembic migration failed with:
`StringDataRightTruncationError: value too long for type character varying(32)` on revision `'0003_add_production_performance_indexes'` (40 chars).

### Root Cause:
Alembic 1.14 default PostgreSQL implementation creates `alembic_version` table with `version_num VARCHAR(32)`. Descriptive migration revision identifiers exceeding 32 characters violate this column width constraint.

### Resolution:
1. Overrode `PostgresqlImpl.version_table_impl` in `backend/alembic/env.py` with `Column("version_num", String(128))`.
2. Added `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);` in `0003_add_production_performance_indexes.py`.
3. Executed migrations up to HEAD (`0007_add_phase10_security_tables`) in 1.38s across all 40 tables.

---

## 4. Issue 4: Next.js Standalone Build EBUSY Directory Lock

### Symptom:
`npm run build` failed with `EBUSY: resource busy or locked, rmdir ...\.next\standalone`.

### Root Cause:
`node .next/standalone/server.js` was active as a background verification process, holding an OS handle lock on the `.next\standalone` directory during the cleanup phase of `next build`.

### Resolution:
Stopped the background node process using `manage_task`. Reran `npm run build`, which compiled all static and dynamic routes in Turbopack in 2.3s with exit code 0.
