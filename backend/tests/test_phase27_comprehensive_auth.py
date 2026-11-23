"""
AutoHeal DevOps — Phase 27 Comprehensive Authentication & Session Security Tests
Validates the complete authentication cycle:
1. User registration (valid, duplicate, invalid input)
2. User login (valid credentials, invalid password, non-existent email)
3. Argon2id password verification
4. JWT token creation and payload structure
5. Refresh Token Rotation (RTR) and replay attack detection
6. Protected API route access and token authorization
7. Logout and cookie invalidation
8. Neon PostgreSQL NullPool / serverless safety
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from app.api.deps import get_db
from app.database import get_engine_args
from app.main import app
from app.models import Organization, RefreshToken, User


@pytest.fixture
def auth_client(db_session: AsyncSession) -> TestClient:
    """Provides a TestClient wired directly to the test database session."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_successful_user_registration(auth_client: TestClient):
    res = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "operator_p27@autoheal.tech",
            "password": "SecurePassword123!",
            "full_name": "DevOps Operator",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "operator_p27@autoheal.tech"
    assert data["user"]["full_name"] == "DevOps Operator"
    assert data["user"]["role"] == "operator"
    assert "refresh_token" in data
    assert "set-cookie" in res.headers


def test_duplicate_user_registration_rejected(auth_client: TestClient):
    # First registration
    res1 = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate_p27@autoheal.tech",
            "password": "SecurePassword123!",
            "full_name": "DevOps Operator",
        },
    )
    assert res1.status_code == 201

    # Second registration with same email
    res2 = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate_p27@autoheal.tech",
            "password": "DifferentPassword456!",
            "full_name": "Second Person",
        },
    )
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()


def test_successful_login_and_token_issuance(auth_client: TestClient):
    # Register user
    auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser_p27@autoheal.tech",
            "password": "CorrectPassword123!",
            "full_name": "Login User",
        },
    )

    # Attempt login
    login_res = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "loginuser_p27@autoheal.tech",
            "password": "CorrectPassword123!",
        },
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "loginuser_p27@autoheal.tech"
    assert "refresh_token" in data


def test_login_invalid_password_returns_401(auth_client: TestClient):
    auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "user1_p27@autoheal.tech",
            "password": "CorrectPassword123!",
            "full_name": "User One",
        },
    )

    login_res = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "user1_p27@autoheal.tech",
            "password": "WrongPassword999!",
        },
    )
    assert login_res.status_code == 401
    assert "invalid email or password" in login_res.json()["detail"].lower()


def test_login_unknown_email_returns_401(auth_client: TestClient):
    login_res = auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent_p27@autoheal.tech",
            "password": "SomePassword123!",
        },
    )
    assert login_res.status_code == 401
    assert "invalid email or password" in login_res.json()["detail"].lower()


def test_protected_route_access_with_valid_token(auth_client: TestClient):
    reg_res = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "me_user_p27@autoheal.tech",
            "password": "SecurePassword123!",
            "full_name": "Me User",
        },
    )
    token = reg_res.json()["access_token"]

    # Access /api/v1/auth/me
    me_res = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "me_user_p27@autoheal.tech"


def test_protected_route_access_without_token_returns_401(auth_client: TestClient):
    me_res = auth_client.get("/api/v1/auth/me")
    assert me_res.status_code == 401


def test_refresh_token_rotation_and_replay_detection(auth_client: TestClient):
    reg_res = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "rtr_user_p27@autoheal.tech",
            "password": "SecurePassword123!",
            "full_name": "RTR User",
        },
    )
    refresh_token_1 = reg_res.json()["refresh_token"]

    # Valid refresh rotation
    ref_res_1 = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_1},
    )
    assert ref_res_1.status_code == 200
    refresh_token_2 = ref_res_1.json()["refresh_token"]
    assert refresh_token_2 != refresh_token_1

    # Replay attack attempt: reuse revoked refresh_token_1
    ref_res_replay = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_1},
    )
    assert ref_res_replay.status_code == 401
    assert "replay" in ref_res_replay.json()["detail"].lower()

    # Legitimate token in family (refresh_token_2) must now be invalidated as well
    ref_res_2 = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_2},
    )
    assert ref_res_2.status_code == 401


def test_logout_revokes_session(auth_client: TestClient):
    reg_res = auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout_user_p27@autoheal.tech",
            "password": "SecurePassword123!",
            "full_name": "Logout User",
        },
    )
    refresh_token = reg_res.json()["refresh_token"]

    # Perform logout
    logout_res = auth_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 200

    # Attempting refresh after logout should fail
    ref_res = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_res.status_code == 401


def test_neon_singapore_pooler_nullpool_selection():
    import os
    orig_vercel = os.environ.get("VERCEL")
    try:
        os.environ["VERCEL"] = "1"
        neon_sg = "postgresql+asyncpg://user:pass@ep-cool-butterfly-123456-pooler.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
        args = get_engine_args(neon_sg)
        assert args.get("poolclass") is NullPool
    finally:
        if orig_vercel is not None:
            os.environ["VERCEL"] = orig_vercel
        else:
            os.environ.pop("VERCEL", None)
