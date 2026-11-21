"""
AutoHeal DevOps — Phase 13 Enterprise Pilot Readiness & Governance Pytest Suite
Verifies:
1. Pilot team onboarding & cryptographically bounded invitations (Admin-only).
2. Incident lifecycle state machine & tamper-evident transition audit trail.
3. Strict resolution safety guards (verified recovery or operator sign-off).
4. SLO scorecard & operational metric calculations (MTTA, MTTR, Availability, Recovery success).
5. RBAC enforcement across Viewer, Operator, and Admin roles.
6. Multi-tenant workspace isolation.
"""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.api.deps import get_db
from app.models.incident import Incident, IncidentTransition
from app.models.organization import Organization, OrganizationInvitation
from app.models.user import User


async def get_phase13_test_data(db_session):
    """Provisions isolated tenant, admin, operator, viewer, and incident for Phase 13 tests."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        slug=f"pilot-org-{uuid.uuid4().hex[:6]}",
        name="Pilot Enterprise Test Org",
        plan="enterprise",
        is_active=True,
    )
    db_session.add(org)

    # Admin user
    admin_id = uuid.uuid4()
    admin_user = User(
        id=admin_id,
        organization_id=org_id,
        email=f"admin-{uuid.uuid4().hex[:6]}@pilot.local",
        full_name="Pilot Admin",
        hashed_password=get_password_hash("AdminPass123!"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)

    # Operator user
    operator_id = uuid.uuid4()
    operator_user = User(
        id=operator_id,
        organization_id=org_id,
        email=f"operator-{uuid.uuid4().hex[:6]}@pilot.local",
        full_name="Pilot Operator",
        hashed_password=get_password_hash("OperatorPass123!"),
        role="operator",
        is_active=True,
    )
    db_session.add(operator_user)

    # Viewer user
    viewer_id = uuid.uuid4()
    viewer_user = User(
        id=viewer_id,
        organization_id=org_id,
        email=f"viewer-{uuid.uuid4().hex[:6]}@pilot.local",
        full_name="Pilot Viewer",
        hashed_password=get_password_hash("ViewerPass123!"),
        role="viewer",
        is_active=True,
    )
    db_session.add(viewer_user)

    await db_session.flush()

    # Generate tokens
    admin_token = create_access_token(str(admin_id), admin_user.email, "admin", str(org_id))
    operator_token = create_access_token(str(operator_id), operator_user.email, "operator", str(org_id))
    viewer_token = create_access_token(str(viewer_id), viewer_user.email, "viewer", str(org_id))

    return {
        "org_id": org_id,
        "admin_user": admin_user,
        "operator_user": operator_user,
        "viewer_user": viewer_user,
        "admin_token": admin_token,
        "operator_token": operator_token,
        "viewer_token": viewer_token,
    }


@pytest.mark.asyncio
async def test_01_pilot_onboarding_admin_can_invite_team_member(db_session):
    """Verifies that an Admin can invite an operator and generate a valid invitation token."""
    data = await get_phase13_test_data(db_session)
    invite_email = f"new-sre-{uuid.uuid4().hex[:6]}@company.com"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/onboarding/invite",
            json={"email": invite_email, "role": "operator"},
            headers={"Authorization": f"Bearer {data['admin_token']}"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["email"] == invite_email
        assert body["role"] == "operator"
        assert "invitation_token" in body
        assert body["is_accepted"] is False
        assert body["organization_id"] == str(data["org_id"])


@pytest.mark.asyncio
async def test_02_pilot_onboarding_operator_cannot_invite(db_session):
    """Verifies RBAC: Operator and Viewer cannot invite new team members (Admin-only)."""
    data = await get_phase13_test_data(db_session)
    invite_email = f"unauthorized-{uuid.uuid4().hex[:6]}@company.com"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Operator attempt
        res_op = await ac.post(
            "/api/v1/onboarding/invite",
            json={"email": invite_email, "role": "operator"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res_op.status_code == 403

        # Viewer attempt
        res_vi = await ac.post(
            "/api/v1/onboarding/invite",
            json={"email": invite_email, "role": "viewer"},
            headers={"Authorization": f"Bearer {data['viewer_token']}"},
        )
        assert res_vi.status_code == 403


@pytest.mark.asyncio
async def test_03_pilot_onboarding_invalid_role_rejected(db_session):
    """Verifies that attempting to grant an unauthorized role returns 400 Bad Request."""
    data = await get_phase13_test_data(db_session)
    invite_email = f"bad-role-{uuid.uuid4().hex[:6]}@company.com"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/onboarding/invite",
            json={"email": invite_email, "role": "super_root_admin"},
            headers={"Authorization": f"Bearer {data['admin_token']}"},
        )
        assert res.status_code == 400
        assert "Invalid role" in res.json()["detail"]


@pytest.mark.asyncio
async def test_04_pilot_onboarding_accept_invitation_flow(db_session):
    """Verifies that a recipient can accept an invitation token and activate their account."""
    data = await get_phase13_test_data(db_session)
    invite_email = f"onboard-{uuid.uuid4().hex[:6]}@company.com"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Admin creates invite
        res = await ac.post(
            "/api/v1/onboarding/invite",
            json={"email": invite_email, "role": "operator"},
            headers={"Authorization": f"Bearer {data['admin_token']}"},
        )
        token = res.json()["invitation_token"]

        # 2. Recipient accepts invite
        accept_res = await ac.post(
            "/api/v1/onboarding/accept-invite",
            json={
                "token": token,
                "full_name": "Onboarded SRE",
                "password": "SecurePassword123!",
            },
        )
        assert accept_res.status_code == 200, accept_res.text
        tokens = accept_res.json()
        assert "access_token" in tokens
        assert tokens["user"]["email"] == invite_email
        assert tokens["user"]["role"] == "operator"
        assert tokens["user"]["organization_id"] == str(data["org_id"])

        # 3. Double-acceptance is rejected
        dup_res = await ac.post(
            "/api/v1/onboarding/accept-invite",
            json={
                "token": token,
                "full_name": "Duplicate Attempt",
                "password": "SecurePassword123!",
            },
        )
        assert dup_res.status_code == 400
        assert "already been accepted" in dup_res.json()["detail"]


@pytest.mark.asyncio
async def test_05_onboarding_checklist_evaluates_readiness(db_session):
    """Verifies that the onboarding checklist endpoint returns structured readiness checkpoints."""
    data = await get_phase13_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/onboarding/checklist",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "completion_percentage" in body
        assert "steps" in body
        assert len(body["steps"]) == 7
        assert body["organization_id"] == str(data["org_id"])


@pytest.mark.asyncio
async def test_06_incident_lifecycle_valid_transitions(db_session):
    """Verifies that valid incident lifecycle transitions succeed and write audit history."""
    data = await get_phase13_test_data(db_session)
    inc_id = f"INC-TEST-{uuid.uuid4().hex[:6]}"

    # Insert test incident in state 'new'
    inc = Incident(
        id=inc_id,
        organization_id=data["org_id"],
        service_id="svc-api",
        service_name="checkout-api",
        title="Canary Incident for Lifecycle Testing",
        severity="high",
        status="new",
        recovery_status="Not started",
        error_rate=2.5,
        threshold=1.0,
        probable_cause="Testing state machine",
        recommended_action="restart_service",
    )
    db_session.add(inc)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Transition: new -> acknowledged
        t1 = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "acknowledged", "reason": "Operator confirmed canary alert on-call"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert t1.status_code == 200, t1.text
        assert t1.json()["status"] == "acknowledged"

        # Transition: acknowledged -> investigation
        t2 = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "investigation", "reason": "Inspecting connection pool logs and P95 latency"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert t2.status_code == 200
        assert t2.json()["status"] == "investigation"

        # Transition: investigation -> diagnosis
        t3 = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "diagnosis", "reason": "AI correlated 503 errors with database lock contention"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert t3.status_code == 200
        assert t3.json()["status"] == "diagnosis"

        # Transition: diagnosis -> approval_pending
        t4 = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "approval_pending", "reason": "Proposed service restart awaiting policy review"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert t4.status_code == 200
        assert t4.json()["status"] == "approval_pending"

        # Transition: approval_pending -> recovery_in_progress
        t5 = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "recovery_in_progress", "reason": "Policy approved: cycling service containers"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert t5.status_code == 200
        assert t5.json()["status"] == "recovery_in_progress"

        # Transition: recovery_in_progress -> recovery_verification
        t6 = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "recovery_verification", "reason": "Containers restarted, verifying SLA"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert t6.status_code == 200
        assert t6.json()["status"] == "recovery_verification"

        # Query transition audit history
        history = await ac.get(
            f"/api/v1/incidents/{inc_id}/transitions",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert history.status_code == 200
        records = history.json()
        assert len(records) == 6
        states = {r["new_state"] for r in records}
        expected_states = {
            "acknowledged",
            "investigation",
            "diagnosis",
            "approval_pending",
            "recovery_in_progress",
            "recovery_verification",
        }
        assert states == expected_states
        assert all(r["actor_role"] == "operator" for r in records)


@pytest.mark.asyncio
async def test_07_incident_lifecycle_invalid_transition_rejected(db_session):
    """Verifies that illegal lifecycle jumps (e.g. new -> resolved without verification) return 409 Conflict."""
    data = await get_phase13_test_data(db_session)
    inc_id = f"INC-ILLEGAL-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id,
        organization_id=data["org_id"],
        service_id="svc-api",
        service_name="checkout-api",
        title="Canary for Illegal Transition",
        severity="medium",
        status="new",
        recovery_status="Not started",
        error_rate=1.8,
        threshold=1.0,
        probable_cause="",
        recommended_action="",
    )
    db_session.add(inc)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Attempt illegal jump: new -> resolved
        res = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "resolved", "reason": "Premature closure attempt"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res.status_code == 409
        assert "Illegal incident transition" in res.json()["detail"]


@pytest.mark.asyncio
async def test_08_incident_resolution_safety_guard(db_session):
    """Verifies safety rule: resolving an incident without verified recovery requires explicit sign_off and detailed reason."""
    data = await get_phase13_test_data(db_session)
    inc_id = f"INC-RESOLVE-{uuid.uuid4().hex[:6]}"

    inc = Incident(
        id=inc_id,
        organization_id=data["org_id"],
        service_id="svc-api",
        service_name="checkout-api",
        title="Resolution Guard Test",
        severity="high",
        status="recovery_verification",
        recovery_status="Verification pending",
        error_rate=0.5,
        threshold=1.0,
        probable_cause="Test",
        recommended_action="restart_service",
    )
    db_session.add(inc)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Attempt to resolve without sign_off
        res_fail = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={"new_status": "resolved", "reason": "Short", "sign_off": False},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res_fail.status_code == 409
        assert "Cannot transition incident to 'resolved'" in res_fail.json()["detail"]

        # Valid operator sign-off with detailed reason
        res_pass = await ac.post(
            f"/api/v1/incidents/{inc_id}/transition",
            json={
                "new_status": "resolved",
                "reason": "Operator manually validated error rate dropped to 0.01% and P95 latency is 42ms.",
                "sign_off": True,
            },
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res_pass.status_code == 200
        assert res_pass.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_09_slo_summary_endpoint(db_session):
    """Verifies that /slo/summary returns compliance scorecard with provenance tags."""
    data = await get_phase13_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/slo/summary",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "overall_compliance_percent" in body
        assert "overall_status" in body
        assert "metrics" in body
        assert len(body["metrics"]) >= 5

        # Check provenance tags
        for m in body["metrics"]:
            assert m["source"] in ("MEASURED", "CALCULATED", "SYNTHETIC_DEMO")
            assert m["status"] in ("compliant", "at_risk", "breached")


@pytest.mark.asyncio
async def test_10_multi_tenant_isolation(db_session):
    """Verifies that users in Org A cannot query or transition incidents in Org B."""
    data = await get_phase13_test_data(db_session)

    # Create Org B and Incident in Org B
    org_b_id = uuid.uuid4()
    org_b = Organization(id=org_b_id, slug=f"org-b-{uuid.uuid4().hex[:6]}", name="Org B", plan="starter")
    db_session.add(org_b)

    inc_b = Incident(
        id=f"INC-ORGB-{uuid.uuid4().hex[:6]}",
        organization_id=org_b_id,
        service_id="svc-b",
        service_name="billing-api",
        title="Org B Incident",
        severity="low",
        status="new",
        recovery_status="Not started",
        error_rate=0.0,
        threshold=1.0,
        probable_cause="",
        recommended_action="",
    )
    db_session.add(inc_b)
    await db_session.commit()

    # User from Org A attempts to access Org B incident
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            f"/api/v1/incidents/{inc_b.id}",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res.status_code == 404

        # Transition attempt
        res_t = await ac.post(
            f"/api/v1/incidents/{inc_b.id}/transition",
            json={"new_status": "investigation", "reason": "Cross-tenant intrusion attempt"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res_t.status_code == 404
