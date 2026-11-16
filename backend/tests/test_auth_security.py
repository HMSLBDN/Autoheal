"""
AutoHeal DevOps — Authentication Security & Vulnerability Regression Tests
Verifies that:
1. The system master secret (SECRET_KEY) cannot be used as an Authorization Bearer token (no bypass).
2. Expired, invalid, or tampered JWT tokens fail closed with 401 Unauthorized.
3. Deactivated accounts cannot authenticate.
4. Report downloads support both PDF and JSON formats.
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.api.deps import get_db
from app.config import get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.incident import Incident

settings = get_settings()


@pytest.fixture
def sec_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_secret_key_cannot_bypass_authentication(sec_client: TestClient, seed_data: dict):
    """
    CRITICAL SECURITY CHECK:
    Passing SECRET_KEY directly in 'Authorization: Bearer <SECRET_KEY>' MUST FAIL with 401.
    Confirms the removal of the master-key public authentication bypass vulnerability.
    """
    # 1. Bearer SECRET_KEY
    response = sec_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {settings.SECRET_KEY}"},
    )
    assert response.status_code == 401
    assert "Invalid or expired" in response.json()["detail"]

    # 2. Query param token=SECRET_KEY
    response = sec_client.get(
        f"/api/v1/events/stream?token={settings.SECRET_KEY}"
    )
    assert response.status_code == 401


def test_expired_jwt_rejected(sec_client: TestClient, seed_data: dict):
    """Expired JWT access token fails closed with 401 Unauthorized."""
    user = seed_data["user_a"]
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "org_id": str(user.organization_id),
        "exp": int(past_time.timestamp()),
        "iat": int((past_time - timedelta(minutes=5)).timestamp()),
        "type": "access",
    }
    expired_token = jwt.encode(
        expired_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )

    response = sec_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "Invalid or expired" in response.json()["detail"]


@pytest.mark.asyncio
async def test_deactivated_user_cannot_access_api(
    sec_client: TestClient, db_session: AsyncSession, seed_data: dict
):
    """Deactivated user account is denied access with 403 Forbidden."""
    user = seed_data["user_a"]
    user.is_active = False
    await db_session.commit()

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )

    response = sec_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"].lower()

    # Restore active status
    user.is_active = True
    await db_session.commit()


@pytest.mark.asyncio
async def test_incident_report_json_and_pdf_formats(
    sec_client: TestClient, db_session: AsyncSession, seed_data: dict
):
    """Incident report download returns valid PDF or JSON depending on format parameter."""
    user = seed_data["user_a"]
    org = seed_data["org_a"]
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Create test incident
    incident = Incident(
        id="INC-REPORT-SEC",
        organization_id=org.id,
        service_id="checkout-api",
        service_name="checkout-api",
        title="Payment Gateway Timeout",
        severity="critical",
        status="resolved",
        detected_at=datetime.now(timezone.utc),
        resolved_at=datetime.now(timezone.utc),
        recovery_status="Resolved",
        error_rate=4.5,
        threshold=1.0,
        probable_cause="Upstream connection saturation",
        recommended_action="restart_service",
    )
    db_session.add(incident)
    await db_session.commit()

    # 1. Download PDF (default)
    pdf_res = sec_client.get(
        f"/api/v1/incidents/{incident.id}/report?format=pdf",
        headers=headers,
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")

    # 2. Download JSON
    json_res = sec_client.get(
        f"/api/v1/incidents/{incident.id}/report?format=json",
        headers=headers,
    )
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    data = json_res.json()
    assert data["incident_id"] == incident.id
    assert data["service_name"] == "checkout-api"
    assert data["status"] == "resolved"
