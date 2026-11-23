"""
AutoHeal DevOps — Phase 22B: Production Deployment Readiness Test Suite
Verifies application lifespan, root health & liveness contracts, CORS preflight for Vercel,
database connection string validation, connection pool configuration, Celery worker resilience,
Prometheus telemetry exposition, and mandatory safe recovery guardrails.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.database import (
    create_database_ssl_context,
    get_engine_args,
    validate_database_url,
)
from app.main import app
from app.worker import celery_app


@pytest.fixture
def readiness_client(db_session: AsyncSession) -> TestClient:
    """Provides a TestClient wired to the test session for production deployment validation."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_01_fastapi_application_metadata():
    """Verifies core FastAPI application properties, API title, and router mounting."""
    settings = get_settings()
    assert app.title == settings.APP_NAME
    assert app.version == settings.APP_VERSION

    # Verify key routes are registered
    route_paths = [r.path for r in app.routes]
    assert "/health" in route_paths
    assert "/metrics" in route_paths
    assert "/" in route_paths
    assert f"{settings.API_V1_STR}/health" in route_paths
    assert f"{settings.API_V1_STR}/auth/login" in route_paths
    assert f"{settings.API_V1_STR}/auth/register" in route_paths
    assert f"{settings.API_V1_STR}/auth/refresh" in route_paths
    assert f"{settings.API_V1_STR}/auth/logout" in route_paths
    assert f"{settings.API_V1_STR}/auth/me" in route_paths


def test_02_production_health_endpoints(readiness_client: TestClient):
    """Verifies root /health, /api/v1/health, and /api/v1/health/liveness probes."""
    # 1. Root /health probe
    res_root = readiness_client.get("/health")
    assert res_root.status_code == 200, res_root.text
    data_root = res_root.json()
    assert data_root["status"] == "healthy"
    assert "timestamp" in data_root
    assert "environment" in data_root
    assert "version" in data_root

    # 2. API v1 /api/v1/health probe
    res_v1 = readiness_client.get("/api/v1/health")
    assert res_v1.status_code == 200, res_v1.text
    data_v1 = res_v1.json()
    assert data_v1["status"] == "healthy"
    assert "timestamp" in data_v1

    # 3. Liveness check
    res_live = readiness_client.get("/api/v1/health/liveness")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "alive"


def test_03_cors_allow_production_and_preview_vercel(readiness_client: TestClient):
    """Verifies CORS headers for the deployed frontend and dynamic Vercel previews."""
    origins = [
        "https://autoheal-omega.vercel.app",
        "https://autoheal-devops.vercel.app",
        "https://autoheal-omega-preview-build-42.vercel.app",
    ]
    for origin in origins:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
        res = readiness_client.options("/api/v1/auth/login", headers=headers)
        assert res.status_code == 200, f"CORS failed for {origin}: {res.text}"
        assert res.headers.get("access-control-allow-origin") == origin
        assert res.headers.get("access-control-allow-credentials") == "true"


def test_04_database_url_validation_and_dialects():
    """Verifies DATABASE_URL validation detects invalid, empty, or unsupported database URIs."""
    # Valid Async PostgreSQL URL
    validate_database_url("postgresql+asyncpg://user:pass@host:5432/autoheal_db")

    # Valid SQLite URL
    validate_database_url("sqlite+aiosqlite:///:memory:")

    # Empty or whitespace URL must fail
    with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
        validate_database_url("")
    with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
        validate_database_url("   ")

    # Unsupported protocol dialect must fail
    with pytest.raises(ValueError, match="does not specify a supported database driver"):
        validate_database_url("mysql+aiomysql://user:pass@host:3306/db")


def test_05_postgresql_pool_configuration():
    """Verifies PostgreSQL engine argument factory configures pre-ping, pool size, and recycling."""
    pg_url = "postgresql+asyncpg://autoheal:secure@db.internal:5432/autoheal_prod"
    args = get_engine_args(pg_url)

    assert args["pool_pre_ping"] is True
    assert "pool_size" in args
    assert "max_overflow" in args
    assert "pool_recycle" in args
    assert "pool_timeout" in args


def test_06_database_ssl_context_logic():
    """Verifies SSLContext creation behaves predictably based on settings."""
    # When no SSL is configured, returns None
    ssl_none = create_database_ssl_context()
    # Should not raise exception
    assert ssl_none is None or hasattr(ssl_none, "verify_mode")


def test_07_celery_worker_production_configuration():
    """Verifies Celery distributed worker has production resilience settings configured."""
    conf = celery_app.conf
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.broker_connection_retry_on_startup is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_time_limit == 180
    assert conf.task_soft_time_limit == 120

    # Beat schedule registration
    beat_schedule = conf.beat_schedule
    assert "periodic-service-monitoring-cycle" in beat_schedule
    assert "periodic-escalation-policy-evaluation" in beat_schedule


def test_08_recovery_simulation_mode_mandatory_guard():
    """
    CRITICAL: Validates that recovery simulation mode is strictly enforced
    and real Docker agent execution is disabled in the production configuration.
    """
    settings = get_settings()
    assert settings.RECOVERY_SIMULATION_MODE is True, (
        "CRITICAL SECURITY FAILURE: RECOVERY_SIMULATION_MODE must be True in production!"
    )
    assert settings.RESTRICTED_DOCKER_AGENT_ENABLED is False, (
        "CRITICAL SECURITY FAILURE: RESTRICTED_DOCKER_AGENT_ENABLED must be False in production!"
    )


def test_09_prometheus_metrics_exposition(readiness_client: TestClient):
    """Verifies /metrics endpoint returns valid Prometheus exposition text."""
    res = readiness_client.get("/metrics")
    assert res.status_code == 200, res.text
    text = res.text
    assert "autoheal_" in text
    assert "# TYPE" in text
    assert "text/plain" in res.headers.get("content-type", "")
