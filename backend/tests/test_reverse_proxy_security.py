"""
AutoHeal DevOps — Reverse Proxy Security & Forwarded Header Trust Tests
Verifies that Uvicorn and FastAPI only accept forwarded headers from explicit,
configured trusted reverse proxies, and strictly rejects wildcard trust in production.
"""

import pytest
from app.config import Settings


def test_default_trusted_proxies():
    """Default configuration must restrict trusted proxies to localhost."""
    settings = Settings(APP_ENV="development")
    assert "127.0.0.1" in settings.FORWARDED_ALLOW_IPS
    assert "::1" in settings.FORWARDED_ALLOW_IPS
    assert "*" not in settings.FORWARDED_ALLOW_IPS


def test_custom_trusted_proxy_cidrs():
    """Custom explicit CIDR ranges must be accepted."""
    settings = Settings(
        APP_ENV="production",
        FORWARDED_ALLOW_IPS="10.0.0.0/8,172.16.0.0/12,192.168.1.100",
        SECRET_KEY="a" * 32,
    )
    assert settings.FORWARDED_ALLOW_IPS == "10.0.0.0/8,172.16.0.0/12,192.168.1.100"


def test_production_rejects_wildcard_proxy_trust():
    """Wildcard '*' must be rejected in production and staging environments."""
    with pytest.raises(ValueError, match="Wildcard FORWARDED_ALLOW_IPS.*is strictly prohibited in production"):
        Settings(
            APP_ENV="production",
            FORWARDED_ALLOW_IPS="*",
            SECRET_KEY="a" * 32,
        )

    with pytest.raises(ValueError, match="Wildcard FORWARDED_ALLOW_IPS.*is strictly prohibited in production"):
        Settings(
            APP_ENV="staging",
            FORWARDED_ALLOW_IPS="'*'",
            SECRET_KEY="a" * 32,
        )
