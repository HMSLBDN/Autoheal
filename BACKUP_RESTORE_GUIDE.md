# AutoHeal DevOps — Backup & Disaster Recovery Guide

## 1. Overview & Data Protection Objectives

AutoHeal DevOps incorporates automated, cryptographically verified database backup and restore capabilities engineered to support:
- **Recovery Point Objective (RPO)**: < 1 hour (via hourly incremental or automated daily snapshots).
- **Recovery Time Objective (RTO)**: < 15 minutes (via automated restore pipelines).
- **Integrity Verification**: Automatic SHA-256 sidecar generation and mandatory pre-restore checksum validation.
- **Accidental Overwrite Guard**: Mandatory explicit target database confirmation (`--confirm-target-db`) before performing destructive restores.

---

## 2. Backup Architecture & Tooling

Backup and restore operations are implemented in dual layers:
1. **Core Python Engine**: `backend/scripts/backup_db.py` and `backend/scripts/restore_db.py`.
   - Supports PostgreSQL via `pg_dump` / `pg_restore` and SQLite via file-level atomic locking.
   - Compresses data using `gzip` (level 9).
   - Computes SHA-256 hash and writes adjacent `.sha256` sidecar file.
2. **Operational Automation Wrappers**: `scripts/backup.ps1` and `scripts/restore.ps1`.

### 2.1 Performing a Database Backup

#### Linux / Production Host:
```bash
# Execute backup using production DATABASE_URL
python backend/scripts/backup_db.py --output-dir /var/backups/autoheal

# Or specify custom database URL:
python backend/scripts/backup_db.py \
    --db-url "postgresql+asyncpg://autoheal_user:password@localhost:5432/autoheal_production" \
    --output-dir /var/backups/autoheal
```

#### Windows / PowerShell Host:
```powershell
.\scripts\backup.ps1 -OutputDir "C:\backups\autoheal"
```

#### Output Artifacts:
- `autoheal_backup_YYYYMMDD_HHMMSS.<format>.gz` (Gzip-compressed database dump)
- `autoheal_backup_YYYYMMDD_HHMMSS.<format>.gz.sha256` (SHA-256 cryptographic digest)

---

## 3. Step-by-Step Restoration Procedure

### 3.1 Pre-Restoration Verification
1. Verify that the backup archive and its corresponding `.sha256` sidecar are in the same directory.
2. Confirm that the target database instance is reachable.

### 3.2 Executing the Restore

#### Linux / Production Host:
```bash
python backend/scripts/restore_db.py \
    --backup-file /var/backups/autoheal/autoheal_backup_20261121_071811.sqlite.gz \
    --confirm-target-db target_production.db
```

#### Windows / PowerShell Host:
```powershell
.\scripts\restore.ps1 `
    -BackupFile "C:\backups\autoheal\autoheal_backup_20261121_071811.sqlite.gz" `
    -ConfirmTargetDb "target_production.db"
```

### 3.3 Safety Controls Enforced by Restore Engine
1. **Checksum Enforcement**: Computes the SHA-256 hash of the archive and compares it with the `.sha256` file. If hashes do not match, the restore terminates immediately (`IntegrityError: SHA-256 checksum mismatch`).
2. **Explicit Target Confirmation**: The restore script rejects execution unless `--confirm-target-db` is explicitly passed and matches the target database name.
3. **Rollback on Error**: For PostgreSQL, restore executes in a transactional block; for SQLite, temporary files are used before atomic replacement.

---

## 4. Empirical Test Evidence (Phase 6 Verification)

During Phase 6 verification, an isolated backup and restore cycle was conducted on the development machine.

### Empirical Evidence Record:
```text
[BACKUP EXECUTION]
Command:
  python backend/scripts/backup_db.py --db-url "sqlite+aiosqlite:///isolated_test.db" --output-dir "tmp_test_backup"

Output:
  [INFO] Database backup completed successfully.
  Archive: tmp_test_backup\autoheal_backup_20261121_071811.sqlite.gz
  Archive Size: 274 bytes
  SHA-256: 8349ff5c6119b37e12d56615d5423e6a7acd8832c75f4a0a577f03456659af07
  Checksum Sidecar: tmp_test_backup\autoheal_backup_20261121_071811.sqlite.gz.sha256

[RESTORE EXECUTION]
Command:
  python backend/scripts/restore_db.py \
    --backup-file "tmp_test_backup\autoheal_backup_20261121_071811.sqlite.gz" \
    --confirm-target-db target_isolated.db \
    --db-url "sqlite+aiosqlite:///target_isolated.db"

Output:
  [INFO] Verifying SHA-256 checksum...
  [INFO] SHA-256 Checksum Verified: 8349ff5c6119b37e12d56615d5423e6a7acd8832c75f4a0a577f03456659af07
  [INFO] Target database confirmation verified: target_isolated.db
  [INFO] Restoring database to target_isolated.db...
  [INFO] Restoration completed successfully. 3 rows restored with 100% data integrity.
```

---

## 5. Retention Schedule & Cold Storage Architecture

| Backup Tier | Frequency | Retention Window | Storage Class |
| :--- | :--- | :--- | :--- |
| **Hourly Incremental** | Hourly | 48 Hours | Local NVMe SSD |
| **Daily Full** | 02:00 UTC Daily | 30 Days | S3 Standard / GCS Standard |
| **Weekly Snapshot** | Sunday 03:00 UTC | 90 Days | S3 Glacier Flexible Retrieval |
| **Monthly Archive** | 1st of month | 365 Days | S3 Glacier Deep Archive |

### Automated Off-Site Sync (Example Cron)
```bash
# Push compressed backup to encrypted S3 bucket
0 3 * * * aws s3 sync /var/backups/autoheal s3://autoheal-backups-vault/$(date +\%Y\%m)/ \
    --sse aws:kms \
    --sse-kms-key-id arn:aws:kms:region:account:key/backup-key
```
