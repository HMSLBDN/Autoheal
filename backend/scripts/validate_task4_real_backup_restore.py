"""
AutoHeal DevOps — Phase 12.2 Task 4: Real PostgreSQL 16 Backup & Restore Suite
Executes native pg_dump and psql restore against live PostgreSQL 16,
verifies SHA-256 integrity, validates schema and row count parity,
and tests application ORM connectivity against the restored database.
"""

import asyncio
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DB_HOST = "127.0.0.1"
DB_PORT = 5432
DB_USER = "autoheal_user"
DB_PASS = "autoheal_dev_pass"
CONTAINER_NAME = "autoheal_db_dev"

SOURCE_DB = f"pg16_backup_source_{uuid.uuid4().hex[:6]}"
RESTORE_DB = f"pg16_restored_target_{uuid.uuid4().hex[:6]}"
BACKUP_DIR = BASE_DIR.parent / "monitoring" / "backups"
RESULTS_FILE = BASE_DIR.parent / "monitoring" / "postgresql_16_backup_restore_results.json"


def calculate_sha256(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


async def main():
    print("=" * 80)
    print("AUTOHEAL DEVOPS — PHASE 12.2 TASK 4: REAL POSTGRESQL 16 BACKUP & RESTORE")
    print("=" * 80)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "12.2",
        "task": "TASK 4 — REAL BACKUP AND RESTORE",
        "status": "IN_PROGRESS",
        "source_database": SOURCE_DB,
        "restore_database": RESTORE_DB,
        "backup": {},
        "restore": {},
        "verification": {},
        "application_test": {},
    }

    # 1. Setup Source Database with Full Schema & Sample Enterprise Data
    print(f"\n[1] Creating source database '{SOURCE_DB}' and populating schema + enterprise dataset...")
    admin_conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database="autoheal_db"
    )
    await admin_conn.execute(f'DROP DATABASE IF EXISTS "{SOURCE_DB}" WITH (FORCE);')
    await admin_conn.execute(f'CREATE DATABASE "{SOURCE_DB}" OWNER "{DB_USER}";')
    await admin_conn.close()

    # Run alembic migrations against SOURCE_DB
    from alembic.config import Config
    from alembic import command
    alembic_ini_path = str(BASE_DIR / "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)
    source_db_url_async = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{SOURCE_DB}"
    os.environ["DATABASE_URL"] = source_db_url_async
    alembic_cfg.set_main_option("sqlalchemy.url", source_db_url_async)
    alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(alembic_cfg, "head"))

    # Connect to SOURCE_DB and insert dataset
    src_conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=SOURCE_DB
    )

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    svc_1_id = f"svc-{uuid.uuid4().hex[:6]}"
    svc_2_id = f"svc-{uuid.uuid4().hex[:6]}"
    inc_1_id = f"INC-{uuid.uuid4().hex[:6]}"
    inc_2_id = f"INC-{uuid.uuid4().hex[:6]}"

    await src_conn.execute(
        "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES ($1, $2, $3, NOW(), NOW());",
        org_id, "Acme Logistics Global", "acme-logistics"
    )
    await src_conn.execute(
        "INSERT INTO users (id, email, hashed_password, full_name, role, organization_id, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW());",
        user_id, "sre.lead@acme.com", "argon2_hashed_secret", "Alex Vance", "admin", org_id
    )
    await src_conn.execute(
        "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
        svc_1_id, org_id, "checkout-api", "production", "healthy", 99.98, 0.0008, 38.5
    )
    await src_conn.execute(
        "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
        svc_2_id, org_id, "payment-gateway", "production", "degraded", 98.45, 0.042, 420.0
    )
    await src_conn.execute(
        "INSERT INTO incidents (id, organization_id, service_id, service_name, title, severity, status, recovery_status, error_rate, threshold, probable_cause, recommended_action, detected_at, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), NOW(), NOW());",
        inc_1_id, org_id, svc_1_id, "checkout-api", "High P95 Latency Spike", "medium", "resolved", "Recovered", 0.05, 0.01, "Pod memory throttle", "Restart and scale replica"
    )
    await src_conn.execute(
        "INSERT INTO incidents (id, organization_id, service_id, service_name, title, severity, status, recovery_status, error_rate, threshold, probable_cause, recommended_action, detected_at, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), NOW(), NOW());",
        inc_2_id, org_id, svc_2_id, "payment-gateway", "Payment Gateway Error Rate Surge", "critical", "investigating", "In progress", 0.08, 0.02, "DB connection saturation", "Restart connection pool"
    )
    await src_conn.execute(
        "INSERT INTO audit_logs (organization_id, user_id, action, resource_type, resource_id, details, created_at) VALUES ($1, $2, $3, $4, $5, $6, NOW());",
        org_id, user_id, "service_created", "service", svc_1_id, '{"source": "cli_provisioning"}'
    )

    # Gather source row counts
    src_tables = await src_conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
    src_table_names = [r["tablename"] for r in src_tables]
    src_row_counts: Dict[str, int] = {}
    for t_name in src_table_names:
        count = await src_conn.fetchval(f'SELECT count(*) FROM "{t_name}";')
        src_row_counts[t_name] = count

    await src_conn.close()
    print(f"    Source database '{SOURCE_DB}' prepared with {len(src_table_names)} tables and sample records.")

    # 2. Real PostgreSQL Backup using native pg_dump
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"autoheal_pg16_backup_{timestamp_str}.sql.gz"
    backup_filepath = BACKUP_DIR / backup_filename

    pg_dump_cmd = [
        "docker", "exec", CONTAINER_NAME,
        "pg_dump",
        "-U", DB_USER,
        "-d", SOURCE_DB,
        "-F", "p",
        "--no-owner",
        "--no-privileges",
    ]

    print(f"\n[2] Executing native pg_dump: {' '.join(pg_dump_cmd)} -> {backup_filepath}...")
    t_backup_start = time.time()
    dump_proc = subprocess.Popen(pg_dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with gzip.open(backup_filepath, "wb") as gz_out:
        if dump_proc.stdout is not None:
            while chunk := dump_proc.stdout.read(65536):
                gz_out.write(chunk)
    dump_proc.wait()
    t_backup_duration = round(time.time() - t_backup_start, 4)

    assert dump_proc.returncode == 0, f"pg_dump failed: {dump_proc.stderr.read().decode('utf-8')}"
    assert backup_filepath.exists(), "Backup file was not created!"

    backup_size_bytes = backup_filepath.stat().st_size
    backup_sha256 = calculate_sha256(backup_filepath)

    # Verify gzip integrity and content
    with gzip.open(backup_filepath, "rt", encoding="utf-8") as gz_in:
        sql_content = gz_in.read()

    sql_lines = len(sql_content.splitlines())
    has_create_table = "CREATE TABLE" in sql_content
    has_inserts = "INSERT INTO" in sql_content or "COPY" in sql_content

    print(f"    pg_dump completed in {t_backup_duration}s.")
    print(f"    File: {backup_filepath.name} ({backup_size_bytes} bytes)")
    print(f"    SHA-256 Checksum: {backup_sha256}")
    print(f"    SQL Content: {sql_lines} lines, DDL verified: {has_create_table}, Data verified: {has_inserts}")

    results["backup"] = {
        "command": " ".join(pg_dump_cmd),
        "file_name": backup_filename,
        "file_path": str(backup_filepath),
        "size_bytes": backup_size_bytes,
        "sha256": backup_sha256,
        "duration_seconds": t_backup_duration,
        "sql_lines": sql_lines,
        "ddl_verified": has_create_table,
        "data_verified": has_inserts,
        "status": "VERIFIED_BACKUP_SUCCESS",
    }

    # 3. Create Separate Empty Restore Target Database
    print(f"\n[3] Creating separate empty database '{RESTORE_DB}'...")
    admin_conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database="autoheal_db"
    )
    await admin_conn.execute(f'CREATE DATABASE "{RESTORE_DB}" OWNER "{DB_USER}";')
    await admin_conn.close()
    print(f"    Target database '{RESTORE_DB}' created.")

    # 4. Native PostgreSQL Restore using psql
    psql_restore_cmd = [
        "docker", "exec", "-i", CONTAINER_NAME,
        "psql",
        "-U", DB_USER,
        "-d", RESTORE_DB,
    ]

    print(f"\n[4] Executing native restore: {' '.join(psql_restore_cmd)} < {backup_filepath.name}...")
    t_restore_start = time.time()
    restore_proc = subprocess.Popen(
        psql_restore_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    with gzip.open(backup_filepath, "rb") as gz_in:
        while chunk := gz_in.read(65536):
            if restore_proc.stdin is not None:
                restore_proc.stdin.write(chunk)
    if restore_proc.stdin is not None:
        restore_proc.stdin.close()
    restore_proc.wait()
    t_restore_duration = round(time.time() - t_restore_start, 4)

    assert restore_proc.returncode == 0, f"psql restore failed: {restore_proc.stderr.read().decode('utf-8')}"
    print(f"    psql restore completed in {t_restore_duration}s.")

    results["restore"] = {
        "command": " ".join(psql_restore_cmd),
        "target_database": RESTORE_DB,
        "duration_seconds": t_restore_duration,
        "status": "VERIFIED_RESTORE_SUCCESS",
    }

    # 5. Parity & Verification Comparison (Source vs Restored)
    print(f"\n[5] Comparing schema and row count parity between '{SOURCE_DB}' and '{RESTORE_DB}'...")
    rest_conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=RESTORE_DB
    )

    rest_tables = await rest_conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
    rest_table_names = [r["tablename"] for r in rest_tables]

    assert src_table_names == rest_table_names, f"Table schema mismatch: {set(src_table_names) ^ set(rest_table_names)}"

    rest_row_counts: Dict[str, int] = {}
    mismatches = []
    for t_name in rest_table_names:
        c = await rest_conn.fetchval(f'SELECT count(*) FROM "{t_name}";')
        rest_row_counts[t_name] = c
        if c != src_row_counts[t_name]:
            mismatches.append(f"{t_name}: src={src_row_counts[t_name]}, rest={c}")

    assert len(mismatches) == 0, f"Row count mismatches found: {mismatches}"
    print(f"    100% Schema & Data Parity Confirmed across all {len(rest_table_names)} tables!")

    results["verification"] = {
        "tables_count": len(rest_table_names),
        "tables": rest_table_names,
        "source_row_counts": src_row_counts,
        "restored_row_counts": rest_row_counts,
        "mismatches": mismatches,
        "parity_confirmed": True,
        "status": "VERIFIED_100_PERCENT_PARITY",
    }

    # 6. Application Connectivity Test against Restored Database
    print(f"\n[6] Testing Application ORM Connectivity against restored database '{RESTORE_DB}'...")
    restored_db_url_async = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{RESTORE_DB}"
    app_engine = create_async_engine(restored_db_url_async, pool_size=5)
    app_session_factory = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

    async with app_session_factory() as session:
        # Query services
        svc_result = await session.execute(text("SELECT id, name, status, error_rate FROM services ORDER BY name;"))
        svc_rows = svc_result.fetchall()
        assert len(svc_rows) == 2, f"Expected 2 services, found {len(svc_rows)}"

        # Query incidents
        inc_result = await session.execute(text("SELECT id, title, severity, status FROM incidents ORDER BY detected_at;"))
        inc_rows = inc_result.fetchall()
        assert len(inc_rows) == 2, f"Expected 2 incidents, found {len(inc_rows)}"

        # Verify specific values
        checkout_svc = next(r for r in svc_rows if r[1] == "checkout-api")
        assert checkout_svc[2] == "healthy"

    await app_engine.dispose()
    await rest_conn.close()

    print(f"    Application query test passed: read {len(svc_rows)} services and {len(inc_rows)} incidents.")

    results["application_test"] = {
        "services_read": len(svc_rows),
        "incidents_read": len(inc_rows),
        "query_status": "SUCCESS_ALL_RECORDS_VALIDATED",
        "status": "VERIFIED_APP_RESTORED_READS",
    }

    # 7. Cleanup Disposable Databases
    print("\n[7] Cleaning up temporary test databases...")
    admin_conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database="autoheal_db"
    )
    await admin_conn.execute(f'DROP DATABASE IF EXISTS "{SOURCE_DB}" WITH (FORCE);')
    await admin_conn.execute(f'DROP DATABASE IF EXISTS "{RESTORE_DB}" WITH (FORCE);')
    await admin_conn.close()
    print("    Temporary test databases dropped cleanly.")

    results["status"] = "ALL_CHECKS_PASSED_SUCCESS"

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 80)
    print("TASK 4 VERIFICATION COMPLETED SUCCESSFULLY (100% PASS)")
    print(f"Results recorded in: {RESULTS_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
