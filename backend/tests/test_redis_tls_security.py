"""
AutoHeal DevOps — Redis TLS & Broker Security Tests
Verifies that Celery Redis connections enforce proper TLS certificate verification,
prevent silent disabling of encryption in production, and support CA bundles and mTLS.
"""

import os
import ssl
import pytest
from app.config import Settings
from app.worker import get_redis_ssl_options


def test_redis_local_dev_connection_no_ssl():
    """Local redis:// connections must not attach SSL configuration."""
    settings = Settings(
        APP_ENV="development",
        REDIS_URL="redis://:redis_dev_pass@localhost:6379/0",
    )
    ssl_opts = get_redis_ssl_options(settings)
    assert ssl_opts is None, "redis:// connections must not enable SSL"


def test_redis_tls_default_verification():
    """rediss:// connections must enforce ssl.CERT_REQUIRED and hostname checking by default."""
    settings = Settings(
        APP_ENV="production",
        REDIS_URL="rediss://:prod_pass@redis.example.com:6380/0",
        SECRET_KEY="a" * 32,
    )
    ssl_opts = get_redis_ssl_options(settings)
    assert ssl_opts is not None, "rediss:// connections must produce SSL options"
    assert ssl_opts["ssl_cert_reqs"] == ssl.CERT_REQUIRED, "Must enforce CERT_REQUIRED"
    assert ssl_opts["ssl_check_hostname"] is True, "Must enforce hostname verification"
    assert "ssl_ca_certs" not in ssl_opts, "Default system trust store when no CA is specified"


from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def _generate_valid_ca_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "autoheal-test-redis-ca"),
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


def test_redis_tls_custom_ca_file(tmp_path):
    """Custom CA certificate bundle must be accepted and passed to SSL options."""
    fake_ca = tmp_path / "ca.crt"
    fake_ca.write_text(_generate_valid_ca_pem(), encoding="utf-8")

    settings = Settings(
        APP_ENV="production",
        REDIS_URL="rediss://:prod_pass@redis.example.com:6380/0",
        REDIS_SSL_CA_CERTS=str(fake_ca),
        SECRET_KEY="a" * 32,
    )
    ssl_opts = get_redis_ssl_options(settings)
    assert ssl_opts is not None
    assert ssl_opts["ssl_ca_certs"] == str(fake_ca)


def test_redis_tls_nonexistent_ca_file_raises():
    """Configuring a non-existent CA bundle must raise FileNotFoundError."""
    settings = Settings(
        APP_ENV="development",
        REDIS_URL="rediss://localhost:6380/0",
        REDIS_SSL_CA_CERTS="/path/to/nonexistent/ca.pem",
    )
    with pytest.raises(FileNotFoundError, match="Configured REDIS_SSL_CA_CERTS file not found"):
        get_redis_ssl_options(settings)


def test_redis_tls_production_rejects_cert_none():
    """In production, attempting to disable certificate verification must raise ValueError."""
    with pytest.raises(ValueError, match="Disabling Redis TLS certificate verification"):
        Settings(
            APP_ENV="production",
            REDIS_URL="rediss://prod.redis.com:6380/0",
            REDIS_SSL_CERT_REQS="none",
            SECRET_KEY="a" * 32,
        )


def test_redis_tls_production_rejects_check_hostname_false():
    """In production, attempting to disable hostname verification must raise ValueError."""
    with pytest.raises(ValueError, match="Disabling Redis TLS hostname verification"):
        Settings(
            APP_ENV="production",
            REDIS_URL="rediss://prod.redis.com:6380/0",
            REDIS_SSL_CHECK_HOSTNAME=False,
            SECRET_KEY="a" * 32,
        )


def test_redis_tls_dev_optional_verification():
    """In development, optional certificate verification is allowed if explicitly configured."""
    settings = Settings(
        APP_ENV="development",
        REDIS_URL="rediss://localhost:6380/0",
        REDIS_SSL_CERT_REQS="optional",
    )
    ssl_opts = get_redis_ssl_options(settings)
    assert ssl_opts is not None
    assert ssl_opts["ssl_cert_reqs"] == ssl.CERT_OPTIONAL
