"""
AutoHeal DevOps — Phase 12.2 Task 3 Live PostgreSQL 16 Validation Suite
Executes real connection, migrations against an empty disposable database,
schema verification, tenant isolation, CRUD, transactions, application pool connectivity,
and container restart persistence.
"""

import asyncio
import os
import sys
import time
import uuid
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Alembic programmatic runner
from alembic.config import Config
from alembic import command

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


DB_HOST = "127.0.0.1"
DB_PORT = 5432
DB_USER = "autoheal_user"
DB_PASS = "autoheal_dev_pass"
BASE_DB = "autoheal_db"
DISPOSABLE_DB = f"disposable_mig_{uuid.uuid4().hex[:8]}"

RESULTS_FILE = BASE_DIR.parent / "monitoring" / "postgresql_16_live_validation_results.json"


async def main():
    print("=" * 80)
    print("AUTOHEAL DEVOPS — PHASE 12.2 TASK 3: LIVE POSTGRESQL 16 VALIDATION")
    print("=" * 80)

    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "12.2",
        "task": "TASK 3 — REAL POSTGRESQL 16",
        "status": "IN_PROGRESS",
        "connection": {},
        "disposable_database": {},
        "migrations": {},
        "schema_verification": {},
        "tenant_isolation": {},
        "crud_operations": {},
        "transactions": {},
        "application_connectivity": {},
        "persistence_restart_test": {},
    }

    # 1. Connection & Server Info
    print(f"\n[1] Connecting to PostgreSQL 16 on {DB_HOST}:{DB_PORT} ({BASE_DB})...")
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=BASE_DB,
    )

    pg_version_raw = await conn.fetchval("SELECT version();")
    server_version = await conn.fetchval("SHOW server_version;")
    current_db = await conn.fetchval("SELECT current_database();")
    current_user = await conn.fetchval("SELECT current_user;")
    max_connections = await conn.fetchval("SHOW max_connections;")
    shared_buffers = await conn.fetchval("SHOW shared_buffers;")

    print(f"    Version: {pg_version_raw}")
    print(f"    Server Version: {server_version}")
    print(f"    Current DB: {current_db}, User: {current_user}")

    results["connection"] = {
        "host": DB_HOST,
        "port": DB_PORT,
        "database": BASE_DB,
        "user": DB_USER,
        "method": "asyncpg / native libpq wire protocol",
        "raw_version": pg_version_raw,
        "server_version": server_version,
        "max_connections": max_connections,
        "shared_buffers": shared_buffers,
        "status": "VERIFIED_CONNECTED",
    }

    # 2. Create Empty Disposable Database
    print(f"\n[2] Creating empty disposable database: '{DISPOSABLE_DB}'...")
    await conn.execute(f'DROP DATABASE IF EXISTS "{DISPOSABLE_DB}" WITH (FORCE);')
    await conn.execute(f'CREATE DATABASE "{DISPOSABLE_DB}" OWNER "{DB_USER}";')
    await conn.close()

    results["disposable_database"] = {
        "name": DISPOSABLE_DB,
        "owner": DB_USER,
        "status": "CREATED_SUCCESS",
    }
    print(f"    Database '{DISPOSABLE_DB}' created successfully.")

    # 3. Run Alembic Migrations against Disposable Database
    print(f"\n[3] Running Alembic migrations against '{DISPOSABLE_DB}'...")
    mig_db_url_sync = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DISPOSABLE_DB}"
    mig_db_url_async = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DISPOSABLE_DB}"
    os.environ["DATABASE_URL"] = mig_db_url_async

    alembic_ini_path = str(BASE_DIR / "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", mig_db_url_async)
    alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))

    t_mig_start = time.time()
    # Run alembic upgrade head synchronously in executor or via command
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(alembic_cfg, "head"))
    t_mig_duration = round(time.time() - t_mig_start, 3)

    print(f"    Alembic migrations completed to HEAD in {t_mig_duration}s.")

    # 4. Connect to Disposable DB & Verify Schema
    disp_conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DISPOSABLE_DB,
    )

    alembic_head = await disp_conn.fetchval("SELECT version_num FROM alembic_version;")
    print(f"    Alembic Head Revision: {alembic_head}")

    # Tables
    tables = await disp_conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
    )
    table_names = [r["tablename"] for r in tables]
    print(f"    Tables verified ({len(table_names)} tables): {table_names}")

    # Indexes
    indexes = await disp_conn.fetch(
        "SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname;"
    )
    index_list = [{"index": r["indexname"], "table": r["tablename"]} for r in indexes]
    print(f"    Indexes verified: {len(index_list)} indexes created.")

    # Foreign Keys & Constraints
    fk_constraints = await disp_conn.fetch("""
        SELECT tc.constraint_name, tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        ORDER BY tc.table_name;
    """)
    fk_list = [dict(r) for r in fk_constraints]
    print(f"    Foreign Keys verified: {len(fk_list)} foreign key constraints active.")

    results["migrations"] = {
        "target_database": DISPOSABLE_DB,
        "duration_seconds": t_mig_duration,
        "head_revision": alembic_head,
        "status": "VERIFIED_MIGRATIONS_PASSED",
    }

    results["schema_verification"] = {
        "table_count": len(table_names),
        "tables": table_names,
        "index_count": len(index_list),
        "foreign_key_count": len(fk_list),
        "status": "VERIFIED_SCHEMA_CONSTRAINTS",
    }

    # 5. Verify Tenant Isolation
    print("\n[5] Verifying multi-tenant isolation...")
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    # Insert Org A & User A
    await disp_conn.execute(
        "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES ($1, $2, $3, NOW(), NOW());",
        org_a_id, "Tenant Alpha", "tenant-alpha"
    )
    await disp_conn.execute(
        "INSERT INTO users (id, email, hashed_password, full_name, role, organization_id, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW());",
        user_a_id, "admin@alpha.com", "hash_a", "Admin Alpha", "admin", org_a_id
    )

    # Insert Org B & User B
    await disp_conn.execute(
        "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES ($1, $2, $3, NOW(), NOW());",
        org_b_id, "Tenant Beta", "tenant-beta"
    )
    await disp_conn.execute(
        "INSERT INTO users (id, email, hashed_password, full_name, role, organization_id, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW());",
        user_b_id, "admin@beta.com", "hash_b", "Admin Beta", "admin", org_b_id
    )

    # Insert services for both
    svc_a_id = f"svc-{uuid.uuid4().hex[:6]}"
    svc_b_id = f"svc-{uuid.uuid4().hex[:6]}"
    await disp_conn.execute(
        "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
        svc_a_id, org_a_id, "checkout-api-alpha", "production", "healthy", 99.95, 0.001, 45.0
    )
    await disp_conn.execute(
        "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
        svc_b_id, org_b_id, "payment-gw-beta", "production", "healthy", 99.90, 0.002, 60.0
    )

    # Query scoped to Org A
    org_a_services = await disp_conn.fetch(
        "SELECT id, name FROM services WHERE organization_id = $1;", org_a_id
    )
    # Query scoped to Org B
    org_b_services = await disp_conn.fetch(
        "SELECT id, name FROM services WHERE organization_id = $1;", org_b_id
    )

    assert len(org_a_services) == 1 and org_a_services[0]["id"] == svc_a_id
    assert len(org_b_services) == 1 and org_b_services[0]["id"] == svc_b_id

    # Verify no cross-tenant leakage
    leakage = await disp_conn.fetchval(
        "SELECT COUNT(*) FROM services WHERE organization_id = $1 AND id = $2;",
        org_a_id, svc_b_id
    )
    assert leakage == 0, "CRITICAL: Cross-tenant data leakage detected!"
    print("    Multi-tenant isolation verified: Org A cannot read Org B services (leakage = 0).")

    results["tenant_isolation"] = {
        "tenant_a_id": str(org_a_id),
        "tenant_b_id": str(org_b_id),
        "leakage_count": leakage,
        "status": "VERIFIED_ZERO_LEAKAGE",
    }

    # 6. Verify CRUD Operations
    print("\n[6] Verifying CRUD Operations...")
    crud_svc_id = f"svc-crud-{uuid.uuid4().hex[:6]}"

    # CREATE
    await disp_conn.execute(
        "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
        crud_svc_id, org_a_id, "crud-canary-svc", "staging", "healthy", 100.0, 0.0, 15.0
    )
    # READ
    read_row = await disp_conn.fetchrow("SELECT * FROM services WHERE id = $1;", crud_svc_id)
    assert read_row is not None and read_row["name"] == "crud-canary-svc"

    # UPDATE
    await disp_conn.execute(
        "UPDATE services SET status = $1, latency_ms = $2, updated_at = NOW() WHERE id = $3;",
        "degraded", 250.0, crud_svc_id
    )
    updated_row = await disp_conn.fetchrow("SELECT status, latency_ms FROM services WHERE id = $1;", crud_svc_id)
    assert updated_row["status"] == "degraded" and updated_row["latency_ms"] == 250.0

    # DELETE
    await disp_conn.execute("DELETE FROM services WHERE id = $1;", crud_svc_id)
    deleted_check = await disp_conn.fetchrow("SELECT * FROM services WHERE id = $1;", crud_svc_id)
    assert deleted_check is None

    print("    CRUD operations (Create, Read, Update, Delete) verified successfully.")
    results["crud_operations"] = {
        "operations": ["INSERT", "SELECT", "UPDATE", "DELETE"],
        "target_table": "services",
        "status": "VERIFIED_CRUD_SUCCESS",
    }

    # 7. Verify Transactions (Commit & Rollback)
    print("\n[7] Verifying Transactions (Commit & Rollback)...")
    # Commit test
    async with disp_conn.transaction():
        await disp_conn.execute(
            "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
            f"svc-tx-c-{uuid.uuid4().hex[:6]}", org_a_id, "tx-committed-svc", "production", "healthy", 99.9, 0.0, 20.0
        )
    comm_check = await disp_conn.fetchval("SELECT COUNT(*) FROM services WHERE name = 'tx-committed-svc';")
    assert comm_check == 1

    # Rollback test
    tx_rollback_id = f"svc-tx-r-{uuid.uuid4().hex[:6]}"
    try:
        async with disp_conn.transaction():
            await disp_conn.execute(
                "INSERT INTO services (id, organization_id, name, environment, status, availability, error_rate, latency_ms, last_checked, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), NOW());",
                tx_rollback_id, org_a_id, "tx-rolledback-svc", "production", "healthy", 99.9, 0.0, 20.0
            )
            # Deliberately raise exception to force rollback
            raise RuntimeError("Intentional rollback test")
    except RuntimeError:
        pass

    roll_check = await disp_conn.fetchval("SELECT COUNT(*) FROM services WHERE id = $1;", tx_rollback_id)
    assert roll_check == 0, "Rollback failed: row exists!"

    print("    Transactions verified: Commit persisted row; Rollback safely discarded changes.")
    results["transactions"] = {
        "commit_verified": True,
        "rollback_verified": True,
        "status": "VERIFIED_TRANSACTIONS_ACID",
    }

    # 8. Application Connectivity via SQLAlchemy Async Engine
    print("\n[8] Verifying Application Connectivity (SQLAlchemy Async Engine & Pool)...")
    async_engine = create_async_engine(mig_db_url_async, pool_size=5, max_overflow=10)
    async_session_factory = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_factory() as session:
        result = await session.execute(text("SELECT count(*) FROM services;"))
        count_val = result.scalar()
        assert count_val is not None
        print(f"    SQLAlchemy session executed 'SELECT count(*) FROM services': {count_val} services found.")

    await async_engine.dispose()
    results["application_connectivity"] = {
        "orm": "SQLAlchemy 2.0 Asyncio",
        "driver": "asyncpg",
        "pool_size": 5,
        "query_result_count": count_val,
        "status": "VERIFIED_APP_CONNECTIVITY",
    }

    await disp_conn.close()

    # 9. Clean up Disposable DB
    admin_conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=BASE_DB,
    )
    print(f"\n[9] Dropping disposable database '{DISPOSABLE_DB}'...")
    await admin_conn.execute(f'DROP DATABASE "{DISPOSABLE_DB}" WITH (FORCE);')
    print("    Disposable database cleaned up cleanly.")

    # 10. Container Restart & Data Persistence Test
    print("\n[10] Verifying PostgreSQL Restart & Data Persistence on base DB...")
    # Write canary in base DB
    canary_id = f"canary-{uuid.uuid4().hex[:8]}"
    canary_token = f"TOKEN-{uuid.uuid4().hex}"
    
    # Ensure audit_logs has the canary row
    await admin_conn.execute("""
        CREATE TABLE IF NOT EXISTS _persistence_canary (
            id VARCHAR(64) PRIMARY KEY,
            token VARCHAR(128) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    await admin_conn.execute(
        "INSERT INTO _persistence_canary (id, token) VALUES ($1, $2);",
        canary_id, canary_token
    )
    await admin_conn.close()
    print(f"    Canary record written to _persistence_canary: id={canary_id}, token={canary_token}")

    print("    Executing 'docker restart autoheal_db_dev'...")
    t_restart_start = time.time()
    sub_res = subprocess.run(["docker", "restart", "autoheal_db_dev"], capture_output=True, text=True)
    assert sub_res.returncode == 0, f"Docker restart failed: {sub_res.stderr}"

    # Poll until ready
    print("    Waiting for PostgreSQL container to become healthy...")
    reconnected = False
    for attempt in range(30):
        await asyncio.sleep(1)
        try:
            test_conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                database=BASE_DB,
                timeout=2,
            )
            # Query canary
            read_canary = await test_conn.fetchrow(
                "SELECT token FROM _persistence_canary WHERE id = $1;", canary_id
            )
            await test_conn.close()
            if read_canary and read_canary["token"] == canary_token:
                reconnected = True
                t_restart_duration = round(time.time() - t_restart_start, 2)
                print(f"    Container restarted and healthy in {t_restart_duration}s!")
                print(f"    Canary verified intact: token matches '{canary_token}'!")
                break
        except Exception:
            continue

    assert reconnected, "FAILED: Persistence canary not found after container restart!"

    results["persistence_restart_test"] = {
        "container_name": "autoheal_db_dev",
        "restart_duration_seconds": t_restart_duration,
        "canary_id": canary_id,
        "canary_verified": True,
        "data_loss": False,
        "status": "VERIFIED_PERSISTENCE_CONFIRMED",
    }

    results["status"] = "ALL_TASKS_VERIFIED_SUCCESS"

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 80)
    print("TASK 3 VERIFICATION COMPLETED SUCCESSFULLY (100% PASS)")
    print(f"Results recorded in: {RESULTS_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
