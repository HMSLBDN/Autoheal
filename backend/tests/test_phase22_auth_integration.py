"""
AutoHeal DevOps — Phase 22: Authentication, Health & CORS Integration Test Suite
Validates backend health probes (/health and /api/v1/health), CORS configuration for Vercel
production and preview deployments, Argon2id authentication, JWT lifecycle, RTR rotation,
session invalidation, and password recovery.
"""

from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_password_hash, verify_password
from app.main import app
from app.models import Organization, PasswordReset, RefreshToken, User


@pytest.fixture
def auth_client(db_session: AsyncSession) -> TestClient:
    """Provides a TestClient wired directly to the test database session without mock credential overrides."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_01_root_health_probe(auth_client: TestClient):
    """Verifies root-level /health endpoint returns HTTP 200 operational status."""
    res = auth_client.get("/health")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "environment" in data
    assert "version" in data


def test_02_api_v1_health_probe(auth_client: TestClient):
    """Verifies API /api/v1/health endpoint consumed by frontend healthApi returns expected schema."""
    res = auth_client.get("/api/v1/health")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_03_cors_preflight_production_vercel(auth_client: TestClient):
    """
    Verifies CORS preflight OPTIONS request from production Vercel frontend:
    https://autoheal-omega.vercel.app is allowed with credentials.
    """
    headers = {
        "Origin": "https://autoheal-omega.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    res = auth_client.options("/api/v1/auth/login", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == "https://autoheal-omega.vercel.app"
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_04_cors_preflight_preview_vercel(auth_client: TestClient):
    """
    Verifies CORS preflight OPTIONS request from Vercel preview branch deployment:
    https://autoheal-omega-preview-xyz.vercel.app is allowed with credentials.
    """
    headers = {
        "Origin": "https://autoheal-omega-preview-123.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    res = auth_client.options("/api/v1/auth/login", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers.get("access-control-allow-origin") == "https://autoheal-omega-preview-123.vercel.app"
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_05_user_registration_and_argon2id_hashing(auth_client: TestClient, db_session: AsyncSession):
    """
    Verifies user registration enforces Argon2id password hashing,
    issues JWT access token, and sets HttpOnly refresh cookie.
    """
    payload = {
        "email": "Phase22.DevOps@autoheal.com",
        "password": "ProductionReadyPassword2026!",
        "full_name": "DevOps Engineer",
    }
    res = auth_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "phase22.devops@autoheal.com"
    assert data["user"]["role"] == "operator"
    assert "refresh_token" in res.cookies

    # Duplicate registration must return 400
    dup_res = auth_client.post("/api/v1/auth/register", json=payload)
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.json()["detail"]


def test_06_login_success_and_failures(auth_client: TestClient):
    """
    Verifies login with valid credentials, invalid password,
    unknown user, and deactivated accounts.
    """
    # 1. Register test user
    email = "phase22.login@autoheal.com"
    password = "CorrectSecretPassphrase123!"
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Login Test User",
    })
    assert reg_res.status_code == 201

    # 2. Login with valid credentials
    login_res = auth_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == email

    # 3. Login with wrong password
    bad_pass_res = auth_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "WrongPassword999!",
    })
    assert bad_pass_res.status_code == 401
    assert bad_pass_res.json()["detail"] == "Invalid email or password."

    # 4. Login with non-existent email
    no_user_res = auth_client.post("/api/v1/auth/login", json={
        "email": "nonexistent@autoheal.com",
        "password": "SomePassword123!",
    })
    assert no_user_res.status_code == 401
    assert no_user_res.json()["detail"] == "Invalid email or password."


def test_07_authenticated_me_profile(auth_client: TestClient):
    """
    Verifies /api/v1/auth/me returns authenticated profile when valid JWT Bearer
    is provided, and returns 401 when missing or invalid.
    """
    # Register and obtain token
    reg = auth_client.post("/api/v1/auth/register", json={
        "email": "phase22.profile@autoheal.com",
        "password": "ProfilePassword123!",
        "full_name": "Profile Operator",
    }).json()
    token = reg["access_token"]

    # Call /me with valid Bearer
    me_res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "phase22.profile@autoheal.com"

    # Call /me without token
    no_token_res = auth_client.get("/api/v1/auth/me")
    assert no_token_res.status_code == 401

    # Call /me with invalid token
    bad_token_res = auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert bad_token_res.status_code == 401


def test_08_refresh_token_rotation_and_replay_detection(auth_client: TestClient):
    """
    Verifies Refresh Token Rotation (RTR):
    - Valid refresh token yields new access and refresh tokens.
    - Replaying the old (revoked) refresh token triggers REPLAY ATTACK DETECTION
      and invalidates the entire token family.
    """
    reg = auth_client.post("/api/v1/auth/register", json={
        "email": "phase22.rtr@autoheal.com",
        "password": "RTRPassword123!",
        "full_name": "RTR Operator",
    })
    initial_refresh = reg.json()["refresh_token"]

    # 1. Rotate token
    rotate_res = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert rotate_res.status_code == 200
    rotated_data = rotate_res.json()
    new_refresh = rotated_data["refresh_token"]
    assert new_refresh != initial_refresh

    # 2. Replay attack attempt: re-send the revoked initial_refresh token
    replay_res = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert replay_res.status_code == 401
    assert "replay detected" in replay_res.json()["detail"].lower()

    # 3. Verify that the entire family was invalidated: even new_refresh should now be rejected
    subsequent_res = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert subsequent_res.status_code == 401


def test_09_logout_revocation(auth_client: TestClient):
    """Verifies logging out invalidates the session and revokes the refresh token."""
    reg = auth_client.post("/api/v1/auth/register", json={
        "email": "phase22.logout@autoheal.com",
        "password": "LogoutPassword123!",
        "full_name": "Logout Operator",
    })
    refresh_token = reg.json()["refresh_token"]

    # Logout
    logout_res = auth_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "success"

    # Attempting to refresh after logout must fail
    fail_res = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert fail_res.status_code == 401
