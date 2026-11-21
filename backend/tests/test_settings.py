"""
AutoHeal DevOps — Settings & Workspace Tests
Tests settings retrieval, role-based update permissions, and audit trail generation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


@pytest.fixture
def settings_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_get_settings_authenticated(settings_client: TestClient, seed_data: dict):
    """Authenticated user receives workspace, user, and non-sensitive environment settings."""
    user = seed_data["user_a"]
    org = seed_data["org_a"]
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = settings_client.get("/api/v1/settings", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # Validates organization fields
    assert data["organization"]["id"] == str(org.id)
    assert data["organization"]["slug"] == org.slug
    assert data["organization"]["name"] == org.name

    # Validates user fields
    assert data["user"]["email"] == user.email
    assert data["user"]["role"] == "operator"

    # Validates environment fields (no secrets exposed!)
    assert "app_env" in data["environment"]
    assert "ai_provider" in data["environment"]
    assert "SECRET_KEY" not in str(data)
    assert "password" not in str(data)


def test_update_settings_user_full_name(settings_client: TestClient, seed_data: dict):
    """Operator can update their own display name."""
    user = seed_data["user_a"]
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = settings_client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"full_name": "Updated Operator Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["full_name"] == "Updated Operator Name"


def test_operator_cannot_update_organization_name(settings_client: TestClient, seed_data: dict):
    """Operator cannot change the organization name (requires admin role)."""
    user = seed_data["user_a"]
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = settings_client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"organization_name": "Hijacked Workspace"},
    )
    assert response.status_code == 403
    assert "Only administrators" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_update_organization_name(
    settings_client: TestClient, db_session: AsyncSession, seed_data: dict
):
    """Admin can update organization name."""
    user = seed_data["user_a"]
    user.role = "admin"
    await db_session.commit()

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = settings_client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"organization_name": "Renamed Enterprise Workspace"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["organization"]["name"] == "Renamed Enterprise Workspace"


def test_settings_fails_safe_on_missing_or_insecure_hmac_secret_in_production():
    """In production, settings validation raises ValueError if ALERTMANAGER_HMAC_SECRET is default or empty."""
    from app.config import Settings

    with pytest.raises(ValueError, match="ALERTMANAGER_HMAC_SECRET is missing or using an insecure default value"):
        Settings(
            APP_ENV="production",
            ALERTMANAGER_HMAC_SECRET="autoheal_alertmanager_webhook_hmac_secret_key_12345",
            SECRET_KEY="test_production_secret_key_min_32_characters_12345",
            REDIS_SSL_CERT_REQS="required",
            REDIS_SSL_CHECK_HOSTNAME=True,
            FORWARDED_ALLOW_IPS="10.0.0.1",
            DB_SSL_MODE="require",
        )

    with pytest.raises(ValueError, match="ALERTMANAGER_HMAC_SECRET is missing or using an insecure default value"):
        Settings(
            APP_ENV="production",
            ALERTMANAGER_HMAC_SECRET="autoheal_dev_alertmanager_webhook_secret_32chars",
            SECRET_KEY="test_production_secret_key_min_32_characters_12345",
            REDIS_SSL_CERT_REQS="required",
            REDIS_SSL_CHECK_HOSTNAME=True,
            FORWARDED_ALLOW_IPS="10.0.0.1",
            DB_SSL_MODE="require",
        )


def test_settings_succeeds_with_strong_hmac_secret_in_production():
    """In production, settings validation passes when strong dedicated secret is provided."""
    from app.config import Settings

    prod_settings = Settings(
        APP_ENV="production",
        ALERTMANAGER_HMAC_SECRET="strong_production_dedicated_webhook_secret_998877",
        SECRET_KEY="test_production_secret_key_min_32_characters_12345",
        REDIS_SSL_CERT_REQS="required",
        REDIS_SSL_CHECK_HOSTNAME=True,
        FORWARDED_ALLOW_IPS="10.0.0.1",
        DB_SSL_MODE="require",
    )
    assert prod_settings.ALERTMANAGER_HMAC_SECRET == "strong_production_dedicated_webhook_secret_998877"

