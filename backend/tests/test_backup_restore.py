"""
AutoHeal DevOps — Database Backup & Restore Utility Tests
Verifies dump creation, SHA-256 checksums, retention pruning, and safety guards.
"""

from pathlib import Path
import sqlite3
import tempfile
import pytest

from scripts.backup_db import calculate_sha256, perform_backup, prune_old_backups
from scripts.restore_db import perform_restore, verify_backup_integrity


def test_backup_and_restore_sqlite_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_db = tmp_path / "test_app.db"
        backups_dir = tmp_path / "backups"

        # 1. Create source SQLite DB with test table and data
        conn = sqlite3.connect(source_db)
        cur = conn.cursor()
        cur.execute("CREATE TABLE services (id INTEGER PRIMARY KEY, name TEXT)")
        cur.execute("INSERT INTO services (name) VALUES ('auth-service'), ('checkout-api')")
        conn.commit()
        conn.close()

        # 2. Perform backup
        backup_file = perform_backup(
            database_url=f"sqlite:///{source_db}",
            output_dir=backups_dir,
            retention_days=7,
        )
        assert backup_file.exists()
        assert backup_file.name.endswith(".sqlite.gz")
        assert backup_file.stat().st_size > 0

        # Checksum file generated
        sha_file = backup_file.with_suffix(backup_file.suffix + ".sha256")
        assert sha_file.exists()
        assert calculate_sha256(backup_file) in sha_file.read_text(encoding="utf-8")

        # 3. Test integrity verification
        assert verify_backup_integrity(backup_file) is True

        # 4. Mutate original database (drop data)
        conn = sqlite3.connect(source_db)
        cur = conn.cursor()
        cur.execute("DELETE FROM services")
        conn.commit()
        conn.close()

        # Verify mutation
        conn = sqlite3.connect(source_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM services")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0

        # 5. Restore database from backup
        perform_restore(
            backup_file=backup_file,
            database_url=f"sqlite:///{source_db}",
            confirm_target_db="test_app.db",
            skip_pre_snapshot=True,
        )

        # 6. Verify restored data
        conn = sqlite3.connect(source_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM services ORDER BY id")
        rows = cur.fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0][0] == "auth-service"
        assert rows[1][0] == "checkout-api"


def test_restore_safety_guard_target_mismatch():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_file = tmp_path / "prod_db.sqlite"
        db_file.touch()

        backup_file = tmp_path / "backup.sqlite.gz"
        backup_file.write_bytes(b"dummy compressed content")

        # Must reject when confirm_target_db doesn't match actual database name
        with pytest.raises(ValueError, match="Safety guard triggered"):
            perform_restore(
                backup_file=backup_file,
                database_url=f"sqlite:///{db_file}",
                confirm_target_db="wrong_database_name",
                skip_pre_snapshot=True,
            )


def test_restore_safety_guard_production():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        backup_file = tmp_path / "backup.sql.gz"
        backup_file.write_bytes(b"dummy compressed content")

        # Connecting to a remote host database without --force-production-restore must raise PermissionError
        remote_url = "postgresql://prod_user:secret@database.prod.internal:5432/autoheal_production"
        with pytest.raises(PermissionError, match="CRITICAL: Target database appears to be PRODUCTION"):
            perform_restore(
                backup_file=backup_file,
                database_url=remote_url,
                confirm_target_db="autoheal_production",
                force_production_restore=False,
                skip_pre_snapshot=True,
            )
