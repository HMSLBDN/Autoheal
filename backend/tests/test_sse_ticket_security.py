"""
AutoHeal DevOps — Single-Use SSE Ticket Security Tests
Verifies cryptographic ticket issuance, atomic single-use burning,
replay prevention, and expiration behavior.
"""

import time
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.services.ticket import SSETicketService, sse_ticket_service


@pytest.mark.asyncio
async def test_sse_ticket_service_unit():
    service = SSETicketService(ttl_seconds=2)
    user_id = "user-12345"
    org_id = "org-67890"

    ticket, ttl = service.issue_ticket(user_id, org_id)
    assert len(ticket) >= 32
    assert ttl == 2

    # 1. First consume succeeds
    consumed = service.consume_ticket(ticket)
    assert consumed is not None
    assert consumed["user_id"] == user_id
    assert consumed["org_id"] == org_id

    # 2. Replay with the same ticket must return None (burned/single-use)
    replay = service.consume_ticket(ticket)
    assert replay is None, "Single-use SSE ticket must NOT be reusable!"


@pytest.mark.asyncio
async def test_sse_ticket_expiration_unit():
    service = SSETicketService(ttl_seconds=1)
    ticket, _ = service.issue_ticket("user-expire", "org-expire")

    # Wait past TTL
    time.sleep(1.1)

    consumed = service.consume_ticket(ticket)
    assert consumed is None, "Expired ticket must not be accepted!"


def test_sse_ticket_endpoints_api(client, seed_data):
    user_a = seed_data["user_a"]
    token = create_access_token(
        user_id=str(user_a.id),
        email=user_a.email,
        role=user_a.role,
        org_id=str(user_a.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Issue ticket endpoint requires auth
    from app.api.deps import get_current_user
    saved_override = app.dependency_overrides.pop(get_current_user, None)
    try:
        unauth_resp = client.post("/api/v1/events/ticket")
        assert unauth_resp.status_code == 401

        # 2. Rejection of bogus or invalid ticket
        bogus_resp = client.get("/api/v1/events/stream?ticket=nonexistent_bogus_ticket_12345")
        assert bogus_resp.status_code == 401
    finally:
        if saved_override:
            app.dependency_overrides[get_current_user] = saved_override

    # 3. Issue ticket with auth succeeds
    ticket_resp = client.post("/api/v1/events/ticket", headers=headers)
    assert ticket_resp.status_code == 200
    ticket_data = ticket_resp.json()
    assert "ticket" in ticket_data
    assert ticket_data["expires_in"] == 60
    ticket = ticket_data["ticket"]

    # 4. Atomic single-use burning verification
    consumed = sse_ticket_service.consume_ticket(ticket)
    assert consumed is not None
    assert consumed["user_id"] == str(user_a.id)

    # 5. Attempt to use the consumed ticket via endpoint -> Must fail with 401
    saved_override = app.dependency_overrides.pop(get_current_user, None)
    try:
        reuse_resp = client.get(f"/api/v1/events/stream?ticket={ticket}")
        assert reuse_resp.status_code == 401
        assert "Invalid, expired, or already consumed" in reuse_resp.text
    finally:
        if saved_override:
            app.dependency_overrides[get_current_user] = saved_override
