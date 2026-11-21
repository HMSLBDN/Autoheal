"""
AutoHeal DevOps — Authentication & Role-Based Access Control (RBAC) Test Suite
Verifies Argon2id hashing, JWT lifecycle, RTR rotation, replay attack detection,
session termination, password recovery, and role-based permissions.
"""

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.main import app
from app.models import Organization, PasswordReset, RefreshToken, User


@pytest.fixture
def auth_client(db_session: AsyncSession) -> TestClient:
    """Provides a TestClient wired directly to the test database session without credential overrides."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_register_success(auth_client: TestClient, db_session: AsyncSession):
    """User registration hashes password with Argon2id, issues JWT, and sets HttpOnly refresh cookie."""
    payload = {
        "email": "Engineer.Alex@example.com",
        "password": "SecurePassword123!",
        "full_name": "Alex Morgan",
    }
    res = auth_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900
    assert data["user"]["email"] == "engineer.alex@example.com"
    assert data["user"]["role"] == "operator"
    assert data["user"]["full_name"] == "Alex Morgan"
    assert data["user"]["is_active"] is True

    # Check refresh cookie is set
    assert "refresh_token" in res.cookies
    assert len(res.cookies["refresh_token"]) > 30


def test_register_duplicate_email(auth_client: TestClient):
    """Registering with an already existing email address must return 400 Bad Request."""
    payload = {
        "email": "duplicate@example.com",
        "password": "ValidPassword123!",
        "full_name": "Original User",
    }
    res1 = auth_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Attempt duplicate registration with same email
    res2 = auth_client.post("/api/v1/auth/register", json={
        "email": "DUPLICATE@example.com",
        "password": "AnotherPassword456!",
        "full_name": "Copycat User",
    })
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


def test_register_role_escalation_prevented(auth_client: TestClient):
    """Users cannot elevate themselves to 'admin' during public self-registration."""
    payload = {
        "email": "hacker@example.com",
        "password": "ValidPassword123!",
        "full_name": "Attacker",
        "role": "admin",
    }
    res = auth_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    assert res.json()["user"]["role"] == "operator"  # Downgraded / enforced to safe role


def test_register_weak_password_validation(auth_client: TestClient):
    """Passwords shorter than 8 characters are rejected by validation schema."""
    payload = {
        "email": "weak@example.com",
        "password": "short",
        "full_name": "Weak Pass User",
    }
    res = auth_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422


def test_login_success(auth_client: TestClient):
    """Login with verified Argon2id credentials returns access token and refresh cookie."""
    # Register first
    auth_client.post("/api/v1/auth/register", json={
        "email": "login_test@example.com",
        "password": "SecretPassword123!",
        "full_name": "Login Tester",
    })

    # Perform login
    res = auth_client.post("/api/v1/auth/login", json={
        "email": "LOGIN_TEST@example.com",
        "password": "SecretPassword123!",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "login_test@example.com"
    assert "refresh_token" in res.cookies


def test_login_invalid_password_anti_enumeration(auth_client: TestClient):
    """Invalid credentials return generic 401 Unauthorized to prevent username enumeration."""
    # Non-existent user
    res1 = auth_client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "WrongPassword123!",
    })
    assert res1.status_code == 401
    assert res1.json()["detail"] == "Invalid email or password."

    # Existing user with wrong password
    auth_client.post("/api/v1/auth/register", json={
        "email": "exists@example.com",
        "password": "CorrectPassword123!",
        "full_name": "Existing User",
    })
    res2 = auth_client.post("/api/v1/auth/login", json={
        "email": "exists@example.com",
        "password": "WrongPassword123!",
    })
    assert res2.status_code == 401
    assert res2.json()["detail"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_login_deactivated_user(auth_client: TestClient, db_session: AsyncSession):
    """Deactivated accounts are denied login with 403 Forbidden."""
    # Create organization and deactivated user directly
    org = Organization(id=uuid.uuid4(), slug="deact-org", name="Deact Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    deact_user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="inactive@example.com",
        full_name="Inactive Person",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=False,
    )
    db_session.add(deact_user)
    await db_session.commit()

    res = auth_client.post("/api/v1/auth/login", json={
        "email": "inactive@example.com",
        "password": "Password123!",
    })
    assert res.status_code == 403
    assert "deactivated" in res.json()["detail"].lower()


def test_get_me_endpoint(auth_client: TestClient):
    """GET /api/v1/auth/me decodes current Bearer JWT and returns user profile."""
    # Register user
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": "profile@example.com",
        "password": "Password123!",
        "full_name": "Profile Owner",
    })
    token = reg_res.json()["access_token"]

    # Request /me with valid token
    res = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "profile@example.com"
    assert data["full_name"] == "Profile Owner"

    # Request /me with invalid token
    res_bad = auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert res_bad.status_code == 401

    # Request /me without token
    res_none = auth_client.get("/api/v1/auth/me")
    assert res_none.status_code == 401


def test_refresh_token_rotation_flow(auth_client: TestClient):
    """Refresh token rotation issues a new access token and rotated refresh token."""
    # Register
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": "rtr_test@example.com",
        "password": "Password123!",
        "full_name": "RTR User",
    })
    initial_refresh_cookie = reg_res.cookies.get("refresh_token")
    assert initial_refresh_cookie is not None

    # Rotate refresh token
    refresh_res = auth_client.post("/api/v1/auth/refresh")
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data
    rotated_refresh_cookie = refresh_res.cookies.get("refresh_token")
    assert rotated_refresh_cookie is not None
    # Rotated cookie must differ from initial cookie
    assert rotated_refresh_cookie != initial_refresh_cookie


def test_refresh_token_replay_attack_detection(auth_client: TestClient):
    """
    CRITICAL SECURITY TEST:
    Replaying an already revoked refresh token triggers family invalidation.
    All tokens in that family must be revoked to stop breach progression.
    """
    # 1. Register to get initial refresh token
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": "replay_victim@example.com",
        "password": "Password123!",
        "full_name": "Replay Target",
    })
    token_v1 = reg_res.cookies.get("refresh_token")

    # 2. Legitimate user rotates token -> v1 is now revoked, v2 is issued
    res_rotate = auth_client.post("/api/v1/auth/refresh")
    assert res_rotate.status_code == 200
    token_v2 = res_rotate.cookies.get("refresh_token")
    assert token_v1 != token_v2

    # 3. Attacker presents the previously used token (v1) -> REPLAY ATTACK!
    auth_client.cookies.set("refresh_token", token_v1)
    replay_res = auth_client.post("/api/v1/auth/refresh")
    assert replay_res.status_code == 401
    assert "replay" in replay_res.json()["detail"].lower()

    # 4. Legitimate token v2 must now ALSO be invalidated because family was revoked!
    auth_client.cookies.set("refresh_token", token_v2)
    subsequent_res = auth_client.post("/api/v1/auth/refresh")
    assert subsequent_res.status_code == 401


def test_logout_revokes_session(auth_client: TestClient):
    """Logout invalidates the refresh token session and clears the cookie."""
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": "logout_user@example.com",
        "password": "Password123!",
        "full_name": "Logout Tester",
    })
    token = reg_res.cookies.get("refresh_token")

    # Call logout
    logout_res = auth_client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "success"

    # Attempting to refresh with the logged out token must fail
    auth_client.cookies.set("refresh_token", token)
    refresh_res = auth_client.post("/api/v1/auth/refresh")
    assert refresh_res.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_flow(auth_client: TestClient, db_session: AsyncSession):
    """
    Verifies full self-service password recovery flow:
    forgot-password -> reset-password -> login with new password -> old sessions terminated.
    """
    email = "reset_user@example.com"
    old_pwd = "OldPassword123!"
    new_pwd = "NewSecurePassword456!"

    # 1. Register user
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": email,
        "password": old_pwd,
        "full_name": "Reset Tester",
    })
    old_refresh_cookie = reg_res.cookies.get("refresh_token")

    # 2. Request password reset
    forgot_res = auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code == 200
    assert "password reset instructions" in forgot_res.json()["message"]

    # 3. Retrieve the generated token from test database
    user_stmt = select(User).where(User.email == email)
    user_res = await db_session.execute(user_stmt)
    user = user_res.scalar_one()

    reset_stmt = select(PasswordReset).where(PasswordReset.user_id == user.id)
    reset_res = await db_session.execute(reset_stmt)
    reset_entry = reset_res.scalar_one()
    assert reset_entry.is_used is False

    # In test environment, recreate a direct valid token test or simulate token match
    from app.core.security import generate_password_reset_token, hash_token
    test_raw_token = generate_password_reset_token()
    reset_entry.token_hash = hash_token(test_raw_token)
    await db_session.commit()

    # 4. Reset password with valid token
    reset_post_res = auth_client.post("/api/v1/auth/reset-password", json={
        "token": test_raw_token,
        "new_password": new_pwd,
    })
    assert reset_post_res.status_code == 200
    assert "reset successfully" in reset_post_res.json()["message"]

    # 5. Login with OLD password must fail
    login_old_res = auth_client.post("/api/v1/auth/login", json={"email": email, "password": old_pwd})
    assert login_old_res.status_code == 401

    # 6. Login with NEW password must succeed
    login_new_res = auth_client.post("/api/v1/auth/login", json={"email": email, "password": new_pwd})
    assert login_new_res.status_code == 200

    # 7. Old sessions must have been revoked by password reset
    auth_client.cookies.set("refresh_token", old_refresh_cookie)
    revoked_refresh = auth_client.post("/api/v1/auth/refresh")
    assert revoked_refresh.status_code == 401


@pytest.mark.asyncio
async def test_rbac_permission_enforcement(auth_client: TestClient, db_session: AsyncSession):
    """
    RBAC Matrix Enforcement:
    - Viewer can read services, incidents, recoveries.
    - Viewer CANNOT approve recovery (403 Forbidden).
    - Viewer CANNOT reject recovery (403 Forbidden).
    - Viewer CANNOT request recovery (403 Forbidden).
    - Operator CAN approve recovery (200 OK).
    """
    # 1. Create organization
    org = Organization(id=uuid.uuid4(), slug="rbac-org", name="RBAC Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    # 2. Create Viewer User
    viewer_user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="viewer@example.com",
        full_name="Viewer User",
        hashed_password=get_password_hash("Password123!"),
        role="viewer",
        is_active=True,
    )
    # 3. Create Operator User
    operator_user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="operator@example.com",
        full_name="Operator User",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add_all([viewer_user, operator_user])
    await db_session.flush()

    # 4. Create Incident & Recovery Action
    from app.models import Incident, RecoveryAction
    incident = Incident(
        id="INC-RBAC-01",
        organization_id=org.id,
        service_id="svc-test",
        service_name="test-api",
        title="RBAC High Latency",
        severity="high",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=2.5,
        threshold=1.0,
    )
    recovery = RecoveryAction(
        id="REC-RBAC-01",
        incident_id=incident.id,
        service_id=incident.service_id,
        service_name=incident.service_name,
        action="Restart application pods",
        status="pending_approval",
        approval_required=True,
        requested_by="System",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add_all([incident, recovery])
    await db_session.commit()

    # Generate JWT tokens for viewer and operator
    viewer_token = create_access_token(str(viewer_user.id), viewer_user.email, viewer_user.role, str(org.id))
    operator_token = create_access_token(str(operator_user.id), operator_user.email, operator_user.role, str(org.id))

    # 5. Viewer can read recoveries
    res_view = auth_client.get("/api/v1/recoveries", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_view.status_code == 200

    # 6. Viewer attempts to approve recovery -> MUST BE 403 FORBIDDEN
    res_approve_denied = auth_client.post(
        f"/api/v1/recoveries/{recovery.id}/approve",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_approve_denied.status_code == 403
    assert "Insufficient permissions" in res_approve_denied.json()["detail"]

    # 7. Viewer attempts to reject recovery -> MUST BE 403 FORBIDDEN
    res_reject_denied = auth_client.post(
        f"/api/v1/recoveries/{recovery.id}/reject",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"reason": "Unauthorized reject attempt"},
    )
    assert res_reject_denied.status_code == 403

    # 8. Viewer attempts to request recovery -> MUST BE 403 FORBIDDEN
    res_request_denied = auth_client.post(
        f"/api/v1/incidents/{incident.id}/recover",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_request_denied.status_code == 403

    # 9. Operator approves recovery -> MUST SUCCEED (200 OK)
    res_approve_allowed = auth_client.post(
        f"/api/v1/recoveries/{recovery.id}/approve",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res_approve_allowed.status_code == 200
    assert res_approve_allowed.json()["status"] == "approved"


def test_cors_preflight_for_vercel_production_and_preview(auth_client: TestClient):
    """CORS headers must be properly returned for Vercel production domain and preview URLs."""
    # Production Vercel domain
    res_prod = auth_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://autoheal-omega.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    assert res_prod.status_code == 200
    assert res_prod.headers.get("access-control-allow-origin") == "https://autoheal-omega.vercel.app"
    assert res_prod.headers.get("access-control-allow-credentials") == "true"

    # Preview Vercel domain
    res_preview = auth_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://autoheal-omega-preview-pr12.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    assert res_preview.status_code == 200
    assert res_preview.headers.get("access-control-allow-origin") == "https://autoheal-omega-preview-pr12.vercel.app"
    assert res_preview.headers.get("access-control-allow-credentials") == "true"

    # Untrusted origin must NOT receive access-control-allow-origin
    res_untrusted = auth_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://autoheal-attacker.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    assert res_untrusted.headers.get("access-control-allow-origin") is None


def test_refresh_token_via_request_body_fallback(auth_client: TestClient):
    """Programs and browsers with blocked cookies can rotate tokens via request body."""
    reg_res = auth_client.post("/api/v1/auth/register", json={
        "email": "body_refresh_test@example.com",
        "password": "Password123!",
        "full_name": "Body Refresh User",
    })
    assert reg_res.status_code == 201
    refresh_token = reg_res.json()["refresh_token"]
    assert refresh_token is not None

    # Clear cookie from client to simulate cookie-blocked browser
    auth_client.cookies.clear()

    # Refresh via request body
    refresh_res = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data
    assert new_data["refresh_token"] != refresh_token


def test_cookie_attributes_in_production_environment(auth_client: TestClient):
    """In production, refresh cookie must use SameSite=None and Secure=True for cross-site browser support."""
    from app.config import get_settings
    current_settings = get_settings()
    original_env = current_settings.APP_ENV
    try:
        current_settings.APP_ENV = "production"
        reg_res = auth_client.post("/api/v1/auth/register", json={
            "email": "prod_cookie_test@example.com",
            "password": "Password123!",
            "full_name": "Prod Cookie User",
        })
        assert reg_res.status_code == 201
        set_cookie_header = reg_res.headers.get("set-cookie", "").lower()
        assert "samesite=none" in set_cookie_header
        assert "secure" in set_cookie_header
        assert "httponly" in set_cookie_header
    finally:
        current_settings.APP_ENV = original_env


def test_sliding_window_rate_limiter_enforcement():
    """Verifies that the auth sliding-window rate limiter throttles abuse after limit threshold."""
    from app.core.rate_limit import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=10)
    key = "test_rate_limit_bruteforce_attacker"

    # 5 allowed requests
    for _ in range(5):
        allowed, retry_after = limiter.is_allowed(key)
        assert allowed is True
        assert retry_after == 0

    # 6th request must be throttled
    allowed, retry_after = limiter.is_allowed(key)
    assert allowed is False
    assert retry_after > 0

    # Reset clears history
    limiter.reset(key)
    allowed, _ = limiter.is_allowed(key)
    assert allowed is True
