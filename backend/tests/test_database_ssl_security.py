"""
AutoHeal DevOps — PostgreSQL SSL / TLS Configuration & Security Tests
Verifies that database connection strings, SSL modes, CA verification,
and asyncpg parameters are securely handled and validated.
"""

import ssl
import pytest
from app.config import Settings
from app.database import create_database_ssl_context, get_engine_args


def test_database_url_normalization_local_unencrypted():
    """Local PostgreSQL URL without SSL parameters must be normalized to postgresql+asyncpg://."""
    settings = Settings(
        APP_ENV="development",
        DATABASE_URL="postgresql://autoheal_user:dev_pass@localhost:5432/autoheal_db",
    )
    assert settings.DATABASE_URL == "postgresql+asyncpg://autoheal_user:dev_pass@localhost:5432/autoheal_db"


def test_database_url_preserves_sqlite_in_memory():
    """sqlite+aiosqlite:///:memory: must be preserved exactly without path or slash corruption."""
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///:memory:"


def test_database_validation_rejects_empty_or_invalid_url():
    """Empty or unparseable database URLs must raise a clear ValueError."""
    from app.database import validate_database_url

    with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
        validate_database_url("")

    with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
        validate_database_url("   ")

    with pytest.raises(ValueError, match="does not specify a supported database driver"):
        validate_database_url("http://not-a-database.com")


def test_database_url_normalization_sslmode_require():
    """sslmode=require must be safely normalized to asyncpg-compatible ssl=require."""
    settings = Settings(
        APP_ENV="production",
        DATABASE_URL="postgres://user:pass@ep-cloud-db.neon.tech/dbname?sslmode=require&application_name=autoheal",
        SECRET_KEY="a" * 32,
    )
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert "ssl=require" in settings.DATABASE_URL
    assert "sslmode" not in settings.DATABASE_URL
    assert "application_name=autoheal" in settings.DATABASE_URL


def test_database_url_normalization_all_valid_sslmodes():
    """All standard PostgreSQL sslmodes must normalize to corresponding ssl parameters."""
    modes = ["prefer", "require", "verify-ca", "verify-full", "disable"]
    for mode in modes:
        settings = Settings(
            APP_ENV="development",
            DATABASE_URL=f"postgres://u:p@db:5432/db?sslmode={mode}",
        )
        assert f"ssl={mode}" in settings.DATABASE_URL
        assert "sslmode=" not in settings.DATABASE_URL


def test_database_url_invalid_sslmode_rejected():
    """Invalid sslmode values must raise ValueError."""
    with pytest.raises(ValueError, match="Invalid PostgreSQL sslmode: 'bypass_tls'"):
        Settings(
            APP_ENV="development",
            DATABASE_URL="postgres://u:p@db:5432/db?sslmode=bypass_tls",
        )


def test_production_rejects_db_ssl_disable():
    """In production, DB_SSL_MODE='disable' must be rejected."""
    with pytest.raises(ValueError, match="Disabling database SSL.*strictly prohibited in production"):
        Settings(
            APP_ENV="production",
            DB_SSL_MODE="disable",
            SECRET_KEY="a" * 32,
        )


from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def _generate_valid_ca_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "autoheal-test-ca"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def test_database_ssl_context_custom_ca(tmp_path):
    """Custom CA certificate generates an SSLContext enforcing CERT_REQUIRED."""
    ca_file = tmp_path / "rds-ca.pem"
    ca_file.write_text(_generate_valid_ca_pem(), encoding="utf-8")

    settings = Settings(
        APP_ENV="production",
        DB_SSL_MODE="verify-full",
        DB_SSL_CA_CERT=str(ca_file),
        SECRET_KEY="a" * 32,
    )
    ctx = create_database_ssl_context(settings)
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_database_ssl_context_verify_ca_disables_hostname_check(tmp_path):
    """verify-ca mode verifies the certificate chain but does not check hostname."""
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text(_generate_valid_ca_pem(), encoding="utf-8")

    settings = Settings(
        APP_ENV="production",
        DB_SSL_MODE="verify-ca",
        DB_SSL_CA_CERT=str(ca_file),
        SECRET_KEY="a" * 32,
    )
    ctx = create_database_ssl_context(settings)
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is False


def test_database_ssl_context_missing_ca_raises():
    """Configuring a non-existent CA bundle raises FileNotFoundError during context creation."""
    settings = Settings(
        APP_ENV="development",
        DB_SSL_MODE="verify-full",
        DB_SSL_CA_CERT="/path/to/missing/ca.pem",
    )
    with pytest.raises(FileNotFoundError):
        create_database_ssl_context(settings)
