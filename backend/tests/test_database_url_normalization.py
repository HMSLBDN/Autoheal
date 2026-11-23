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
