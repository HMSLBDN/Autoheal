# PostgreSQL 16 Backup & Restore Evidence

**Method:** Native PostgreSQL CLI (`pg_dump` and `psql`)  
**Engine:** PostgreSQL 16.16 Alpine  
**Timestamp:** 2026-11-21T19:29:30+05:30  
**Status:** **VERIFIED**  

---

## 1. Backup Execution Evidence

### Native Command Executed:
```bash
docker exec autoheal_db_dev pg_dump \
  -U autoheal_user \
  -d pg16_backup_source_df6758 \
  -F p \
  --no-owner \
  --no-privileges | gzip > monitoring/backups/autoheal_pg16_backup_20261121_192929.sql.gz
```

### Metrics & Properties:
- **Measured Backup Duration:** **0.4790 seconds**
- **Output File:** `monitoring/backups/autoheal_pg16_backup_20261121_192929.sql.gz`
- **Compressed File Size:** `9,648 bytes` (9.42 KB)
- **Uncompressed SQL Lines:** `2,924 lines`
- **SHA-256 Checksum:** `1695dcdf203728ef416cf6f77c544b40ec0c96980a670236c8b18273dbe8238c`
- **Integrity Validation:** DDL statements present (`CREATE TABLE`), Table data present (`COPY` / `INSERT INTO`). Gzip checksum validation passed.

---

## 2. Restore Execution Evidence

### Native Command Executed:
```bash
gzip -dc monitoring/backups/autoheal_pg16_backup_20261121_192929.sql.gz | \
  docker exec -i autoheal_db_dev psql \
  -U autoheal_user \
  -d pg16_restored_target_ce735d
```

### Metrics & Properties:
- **Measured Restore Duration:** **1.1453 seconds**
- **Target Database:** `pg16_restored_target_ce735d` (isolated, initially empty)
- **Exit Code:** `0`

---

## 3. Parity & Data Verification Comparison

Every table in the source database was compared with the restored target database:

| Metric | Source Database | Restored Database | Parity Match |
| :--- | :--- | :--- | :--- |
| **Total Table Count** | `40` | `40` | **100% MATCH** |
| **`organizations` Row Count** | `1` | `1` | **100% MATCH** |
| **`users` Row Count** | `1` | `1` | **100% MATCH** |
| **`services` Row Count** | `2` | `2` | **100% MATCH** |
| **`incidents` Row Count** | `2` | `2` | **100% MATCH** |
| **`audit_logs` Row Count** | `1` | `1` | **100% MATCH** |
| **Total Row Mismatches** | `0` | `0` | **ZERO MISMATCHES** |

---

## 4. Application Connectivity against Restored Database

An asynchronous SQLAlchemy 2.0 connection pool was established to `pg16_restored_target_ce735d`:
```python
engine = create_async_engine("postgresql+asyncpg://autoheal_user:autoheal_dev_pass@127.0.0.1:5432/pg16_restored_target_ce735d")
# Queried services: 2 services read and validated
# Queried incidents: 2 incidents read and validated (including checkout-api healthy status)
```
- **Result:** Application successfully executed reads against the restored database with zero errors.
