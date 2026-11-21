# AutoHeal DevOps — Database Management, Backup & Restore Guide

This guide details the PostgreSQL connection pool architecture, Alembic database migrations, automated backup pipelines, and protected restore procedures.

---

## 1. Database Architecture & Connection Pooling

AutoHeal DevOps utilizes PostgreSQL 16 (or SQLite with StaticPool during testing) managed via SQLAlchemy 2.0 async engine (`postgresql+asyncpg://`):

### 1.1 Connection Pool Settings (`app.database` & `app.config`)
- **`DB_POOL_SIZE` (default: 20)**: Number of persistent database connections maintained in the pool.
- **`DB_MAX_OVERFLOW` (default: 10)**: Maximum number of temporary connections created above `pool_size` during traffic bursts.
- **`DB_POOL_TIMEOUT` (default: 30s)**: Seconds to wait for a connection from the pool before raising a timeout exception.
- **`DB_POOL_RECYCLE` (default: 1800s / 30m)**: Replaces idle connections older than 30 minutes to prevent stale socket disconnects.
- **`pool_pre_ping=True`**: Executes a lightweight test (`SELECT 1`) on checked-out connections to safely drop and reconnect severed TCP sockets before handing them to requests.

### 1.2 Multi-Tenant Schema (16 Tables)
1. `organizations`: Tenant accounts.
2. `users`: Multi-tenant user accounts with Argon2id passwords and RBAC roles (`admin`, `operator`, `viewer`).
3. `services`: Monitored infrastructure services with health status.
4. `service_metrics`: Time-series observations (error rate, latency, cpu, memory).
5. `incidents`: Detected infrastructure incidents with deduplication fingerprints.
6. `incident_evidence`: Correlated log entries, metric snapshots, and traces.
7. `incident_events`: Audit log of lifecycle transitions.
8. `recovery_actions`: Proposed and executed remediation operations.
9. `recovery_results`: Cryptographic execution receipts and post-recovery health metrics.
10. `user_refresh_tokens`: Cryptographic refresh tokens for RTR.
11. Additional audit, policy, settings, and telemetry tables.

---

## 2. Database Migrations (Alembic)

Database schema evolution is managed with Alembic.

### 2.1 Applying Migrations
Apply all pending migrations to upgrade the schema to the latest version:

**Windows PowerShell:**
```powershell
$env:PYTHONPATH="backend"
alembic -c backend/alembic.ini upgrade head
```

**Linux / macOS:**
```bash
PYTHONPATH=backend alembic -c backend/alembic.ini upgrade head
```

### 2.2 Checking Migration Status
```powershell
alembic -c backend/alembic.ini current
alembic -c backend/alembic.ini history --verbose
```

### 2.3 Creating a New Migration
```powershell
alembic -c backend/alembic.ini revision --autogenerate -m "add_new_column_to_services"
```

---

## 3. Automated Backup Pipeline

Backups are executed via `scripts/backup.ps1` (wrapper around `backend/scripts/backup_db.py`).

### 3.1 Features
- **Compressed Artifacts**: Generates timestamped `.sql.gz` (PostgreSQL) or `.sqlite.gz` (SQLite) archives.
- **Integrity Validation**: Computes an SHA-256 checksum and saves it adjacent to the archive as `<filename>.sha256`.
- **Retention Pruning**: Automatically prunes backup archives older than the specified retention window (default: 7 days).
- **Dry-Run Mode**: Allows operators to preview backup generation and retention pruning without modifying disk.

### 3.2 Running a Backup
```powershell
# Run a standard backup to default ./backups directory with 7-day retention
.\scripts\backup.ps1

# Custom output directory and retention window
.\scripts\backup.ps1 -OutputDir "./custom_backups" -RetentionDays 14

# Dry-run preview
.\scripts\backup.ps1 -DryRun
```

Example output:
```text
[INFO] Starting database backup...
[INFO] Source Database: autoheal_db (PostgreSQL)
[INFO] Creating backup archive: ./backups/autoheal_backup_20261121_110000.sql.gz
[INFO] Backup completed successfully (Size: 1.4 MB)
[INFO] SHA-256 Checksum: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
[INFO] Pruning backups older than 7 days: 0 files removed.
```

---

## 4. Protected Database Restore Procedure

Restoring a database replaces active schema and data. AutoHeal enforces **three strict safety guards** in `scripts/restore.ps1`:

### 4.1 Safety Guards
1. **Target Confirmation Guard (`-ConfirmTargetDb`)**:
   The operator must explicitly pass `-ConfirmTargetDb <name>` matching the active database name. Mismatches abort immediately.
2. **Production Safeguard (`-ForceProductionRestore`)**:
   If the target host is not `localhost` or `APP_ENV=production`, the command requires `-ForceProductionRestore` to prevent accidental staging/production overwrites.
3. **Automated Safety Snapshot**:
   Before modifying a single table, the restore pipeline automatically generates a fresh pre-restore backup of the live database, ensuring instant rollback capability if the restore fails.
4. **SHA-256 Checksum Verification**:
   The restore pipeline validates the `.sha256` integrity checksum before decompressing and executing SQL commands.

### 4.2 Executing a Restore
```powershell
# Safe restore on development database
.\scripts\restore.ps1 `
    -BackupFile "./backups/autoheal_backup_20261121_110000.sql.gz" `
    -ConfirmTargetDb "autoheal_db"

# Restore on production database (requires explicit safety flags)
.\scripts\restore.ps1 `
    -BackupFile "./backups/autoheal_backup_20261121_110000.sql.gz" `
    -ConfirmTargetDb "autoheal_prod_db" `
    -ForceProductionRestore
```

---

## 5. Automated Verification & Testing

The backup and restore pipeline is verified under CI in `backend/tests/test_backup_restore.py`:
- `test_backup_creates_compressed_file_and_checksum`: Verifies gzip compression and SHA-256 hash.
- `test_backup_retention_pruning`: Verifies aged file removal.
- `test_restore_fails_on_unconfirmed_target`: Verifies confirmation requirement.
- `test_restore_verifies_checksum_integrity`: Verifies corrupted file rejection.
- `test_restore_creates_pre_restore_snapshot`: Verifies automatic pre-restore backup.
