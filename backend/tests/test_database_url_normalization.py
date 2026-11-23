"""
AutoHeal DevOps — Neon & Asyncpg DATABASE_URL Normalization Tests
Verifies that DATABASE_URL strings (especially Neon PostgreSQL connection strings with libpq query parameters)
are normalized safely for SQLAlchemy's asyncpg dialect:
1. Strips channel_binding=require.
2. Translates sslmode=require into ssl=require.
3. Strips other unsupported libpq parameters (endpoint, connect_timeout, options).
4. Preserves user, password (including special characters), host, port, dbname.
5. Preserves Neon pooled connection hosts (-pooler).
6. Preserves SQLite URLs untouched.
7. Validates that create_async_engine() can instantiate without TypeError: 'channel_binding'.
"""

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import Settings


def test_neon_url_with_channel_binding_and_sslmode():
    """Neon console often copies: postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require&channel_binding=require"""
    raw_url = "postgresql://neondb_owner:npg_SecretPass123@ep-cool-butterfly-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    normalized = Settings.assemble_database_url(raw_url)

    parsed = make_url(normalized)
    assert parsed.drivername == "postgresql+asyncpg"
    assert parsed.username == "neondb_owner"
    assert parsed.password == "npg_SecretPass123"
    assert parsed.host == "ep-cool-butterfly-123456.ap-southeast-1.aws.neon.tech"
    assert parsed.database == "neondb"
    assert parsed.query.get("ssl") == "require"
    assert "channel_binding" not in parsed.query
    assert "sslmode" not in parsed.query

    # Verify that create_async_engine does not fail during construction
    engine = create_async_engine(normalized)
    assert engine is not None


def test_neon_pooled_connection_url():
    """Neon pooled connection string with -pooler and endpoint parameter."""
    raw_url = "postgresql://user:pass@ep-cool-butterfly-123456-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&endpoint=ep-cool-butterfly-123456"
    normalized = Settings.assemble_database_url(raw_url)

    parsed = make_url(normalized)
    assert parsed.drivername == "postgresql+asyncpg"
    assert "-pooler" in parsed.host
    assert parsed.query.get("ssl") == "require"
    assert "endpoint" not in parsed.query
    assert "sslmode" not in parsed.query


def test_neon_url_with_multiple_libpq_parameters():
    """Multiple libpq parameters including connect_timeout, channel_binding, keepalives."""
    raw_url = "postgres://usr:pwd@host.neon.tech:5432/db?sslmode=require&channel_binding=require&connect_timeout=10&keepalives=1&endpoint=ep-xyz"
    normalized = Settings.assemble_database_url(raw_url)

    parsed = make_url(normalized)
    assert parsed.drivername == "postgresql+asyncpg"
    assert parsed.port == 5432
    assert parsed.query.get("ssl") == "require"
    assert "channel_binding" not in parsed.query
    assert "connect_timeout" not in parsed.query
    assert "keepalives" not in parsed.query
    assert "endpoint" not in parsed.query


def test_credentials_with_special_characters():
    """Password with url-encoded special characters like @, !, $, etc."""
    raw_url = "postgresql://user%40company:p%40ss%23%24word@neon-host.tech:5432/mydb?sslmode=require"
    normalized = Settings.assemble_database_url(raw_url)

    parsed = make_url(normalized)
    assert parsed.username == "user@company"
    assert parsed.password == "p@ss#$word"
    assert parsed.query.get("ssl") == "require"


def test_local_postgresql_url():
    """Local connection string without SSL parameters."""
    raw_url = "postgresql://local_user:local_pass@localhost:5432/local_db"
    normalized = Settings.assemble_database_url(raw_url)

    parsed = make_url(normalized)
    assert parsed.drivername == "postgresql+asyncpg"
    assert parsed.host == "localhost"
    assert parsed.port == 5432
    assert "ssl" not in parsed.query


def test_sqlite_url_preserved():
    """SQLite memory and file URLs must remain completely untouched."""
    sqlite_memory = "sqlite+aiosqlite:///:memory:"
    assert Settings.assemble_database_url(sqlite_memory) == sqlite_memory

    sqlite_file = "sqlite+aiosqlite:///test.db"
    assert Settings.assemble_database_url(sqlite_file) == sqlite_file


def test_invalid_sslmode_raises_value_error():
    """Invalid sslmode should raise ValueError."""
    bad_url = "postgresql://user:pass@host/db?sslmode=super-secure"
    with pytest.raises(ValueError, match="Invalid PostgreSQL sslmode"):
        Settings.assemble_database_url(bad_url)


def test_engine_creation_verifies_channel_binding_never_passed():
    """Ensure that create_async_engine on normalized Neon URL does not throw TypeError."""
    raw_url = "postgresql://myuser:mypass@ep-test-pooler.neon.tech/neondb?sslmode=require&channel_binding=require"
    normalized = Settings.assemble_database_url(raw_url)
    engine = create_async_engine(normalized)
    # The dialect connect_args must not contain channel_binding
    assert "channel_binding" not in engine.url.query


def test_prepare_database_url_and_args_with_application_name_and_options():
    """
    Verifies prepare_database_url_and_args extracts application_name into server_settings
    and strips options, so asyncpg.connect() never encounters unexpected keyword arguments.
    """
    from app.database import prepare_database_url_and_args

    raw_url = "postgres://user:pass@ep-cloud-db.neon.tech/dbname?sslmode=require&application_name=autoheal&options=endpoint%3Dep-xyz"
    clean_url, extra_args = prepare_database_url_and_args(raw_url)

    parsed = make_url(clean_url)
    assert parsed.drivername == "postgresql+asyncpg"
    assert "application_name" not in parsed.query
    assert "options" not in parsed.query
    assert parsed.query.get("ssl") == "require"

    assert "connect_args" in extra_args
    assert extra_args["connect_args"]["server_settings"]["application_name"] == "autoheal"


@pytest.mark.asyncio
async def test_database_health_check_function():
    """Verifies that check_database_health returns structured status without raising unhandled errors."""
    from app.database import check_database_health
    result = await check_database_health()
    assert "database" in result
    assert "schema" in result
    assert result["database"] in ("connected", "unreachable", "not_configured")
    assert result["schema"] in ("ready", "pending", "error", "not_configured")


def test_registration_database_unavailable_returns_503(client):
    """Verifies that database connection failures during registration return HTTP 503."""
    from unittest.mock import AsyncMock, patch
    from sqlalchemy.exc import OperationalError
    from app.api.deps import get_db

    async def mock_failing_db():
        session = AsyncMock()
        session.execute.side_effect = OperationalError("connection refused", {}, Exception("db down"))
        yield session

    from app.main import app
    app.dependency_overrides[get_db] = mock_failing_db
    try:
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test-failure@autoheal.dev",
                "password": "Password123!",
                "full_name": "Test User",
            },
        )
        assert res.status_code == 503, res.text
        assert "Database service temporarily unavailable" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_registration_integrity_error_race_condition(client):
    """Verifies that duplicate account collisions (IntegrityError) return HTTP 400."""
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.exc import IntegrityError
    from app.api.deps import get_db

    async def mock_colliding_db():
        session = AsyncMock()
        session.add = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_res
        session.flush.side_effect = IntegrityError("duplicate key value", {}, Exception("unique violation"))
        yield session

    from app.main import app
    app.dependency_overrides[get_db] = mock_colliding_db
    try:
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": "collision@autoheal.dev",
                "password": "Password123!",
                "full_name": "Test User",
            },
        )
        assert res.status_code == 400, res.text
        assert "already exists" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_request_id_correlation_propagation(client):
    """Verifies that X-Request-ID and x-vercel-id are preserved and propagated in responses."""
    test_req_id = "req-custom-trace-id-12345"
    res = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": test_req_id, "x-vercel-id": "iad1::test-vercel-invocation"},
    )
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == test_req_id
    assert res.headers.get("x-vercel-id") == "iad1::test-vercel-invocation"
