"""
AutoHeal DevOps — Unit and Integration Tests for db_diagnostic.py
Verifies:
1. DNS failure is identified correctly.
2. TCP timeout / unreachable port is identified correctly.
3. Authentication failure (InvalidPasswordError) is identified cleanly without leaking passwords.
4. Successful SELECT 1 is recognised.
5. Empty Alembic revision (fresh database) is distinguished from a failed connection.
6. A failed connection always marks ready_for_migration=False.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.db_diagnostic import (
    run_dns_check,
    run_tcp_check,
    run_async_database_checks,
    run_full_diagnostics,
)


def test_dns_failure_identified():
    """Unresolvable host must fail at DNS stage."""
    result = run_dns_check("ep-definitely-does-not-exist-xyz-9999.neon.tech")
    assert result["success"] is False
    assert result["mode"] == "failed"
    assert "DNS resolution failed" in result["message"]


def test_tcp_timeout_identified():
    """Non-routable IP (TEST-NET-1: 192.0.2.1) must report TCP timeout."""
    result = run_tcp_check("192.0.2.1", port=5432, timeout_seconds=0.5)
    assert result["success"] is False
    assert "timed out" in result["message"] or "failed" in result["message"]


@pytest.mark.asyncio
async def test_auth_failure_identified_without_leaking_secret():
    """Simulated InvalidPasswordError must return error_stage='AUTH' and generic message."""
    import asyncpg

    with patch("app.db_diagnostic.create_async_engine") as mock_engine_factory:
        mock_eng = MagicMock()
        # Mock connection throwing InvalidPasswordError
        mock_conn_ctx = AsyncMock()
        mock_conn_ctx.__aenter__.side_effect = asyncpg.exceptions.InvalidPasswordError(
            "password authentication failed for user 'test_owner'"
        )
        mock_eng.connect.return_value = mock_conn_ctx
        mock_eng.dispose = AsyncMock()
        mock_engine_factory.return_value = mock_eng

        result = await run_async_database_checks("postgresql+asyncpg://test_owner:secret_pass@host/db", {})
        assert result["connect_success"] is False
        assert result["error_stage"] == "AUTH"
        assert result["error_type"] == "AUTHENTICATION_FAILED"
        assert "Password authentication failed" in result["error_message"]
        assert "secret_pass" not in result["error_message"]
        assert "secret_pass" not in result["details"]


@pytest.mark.asyncio
async def test_successful_select_1_and_empty_alembic_db():
    """Successful connection with no alembic_version table must report is_empty_db=True."""
    with patch("app.db_diagnostic.create_async_engine") as mock_engine_factory:
        mock_eng = MagicMock()
        mock_conn = AsyncMock()

        # Mock SELECT 1 -> returns 1
        mock_select_res = MagicMock()
        mock_select_res.scalar.return_value = 1

        # Mock table lookup -> alembic_version table not found
        mock_table_res = MagicMock()
        mock_table_res.scalar.return_value = None

        mock_conn.execute.side_effect = [mock_select_res, mock_table_res]

        mock_conn_ctx = AsyncMock()
        mock_conn_ctx.__aenter__.return_value = mock_conn
        mock_eng.connect.return_value = mock_conn_ctx
        mock_eng.dispose = AsyncMock()
        mock_engine_factory.return_value = mock_eng

        result = await run_async_database_checks("postgresql+asyncpg://user:pass@host/db", {})
        assert result["connect_success"] is True
        assert result["select_success"] is True
        assert result["has_alembic_table"] is False
        assert result["is_empty_db"] is True
        assert result["current_revision"] is None


@pytest.mark.asyncio
async def test_successful_select_1_with_existing_alembic_revision():
    """Successful connection with alembic_version table must report revision string."""
    with patch("app.db_diagnostic.create_async_engine") as mock_engine_factory:
        mock_eng = MagicMock()
        mock_conn = AsyncMock()

        # Mock SELECT 1 -> returns 1
        mock_select_res = MagicMock()
        mock_select_res.scalar.return_value = 1

        # Mock table lookup -> alembic_version exists
        mock_table_res = MagicMock()
        mock_table_res.scalar.return_value = "alembic_version"

        # Mock revision lookup -> 0010_add_phase16_recovery_classification
        mock_rev_res = MagicMock()
        mock_rev_res.scalar.return_value = "0010_add_phase16_recovery_classification"

        mock_conn.execute.side_effect = [mock_select_res, mock_table_res, mock_rev_res]

        mock_conn_ctx = AsyncMock()
        mock_conn_ctx.__aenter__.return_value = mock_conn
        mock_eng.connect.return_value = mock_conn_ctx
        mock_eng.dispose = AsyncMock()
        mock_engine_factory.return_value = mock_eng

        result = await run_async_database_checks("postgresql+asyncpg://user:pass@host/db", {})
        assert result["connect_success"] is True
        assert result["select_success"] is True
        assert result["has_alembic_table"] is True
        assert result["is_empty_db"] is False
        assert result["current_revision"] == "0010_add_phase16_recovery_classification"


def test_failed_connection_never_treated_as_empty_db():
    """When target host is non-Neon or DNS fails, ready_for_migration must be False."""
    res = run_full_diagnostics("postgresql+asyncpg://user:pass@non-neon-host.com/db")
    assert res["ready_for_migration"] is False
    assert res["overall_status"] == "FAILED"
    assert res["failing_stage"] == "target_verification"
