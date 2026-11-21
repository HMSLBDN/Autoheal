"""
AutoHeal DevOps — Phase 10 Enterprise Test Suite
Verifies all 30 required scenarios across enterprise SSO, session security,
agent mTLS PKI, OpenTelemetry distributed tracing, Prometheus observability,
supply chain SBOM, database hardening, and multi-tenant isolation.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import ssl
import sys
import time
import uuid
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Ensure root directory is on sys.path for importing scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.main import app
from app.api.deps import get_current_org, get_current_user, get_db
from app.core.security import (
    create_access_token,
    encrypt_secret,
    decrypt_secret,
    mask_secret,
    generate_refresh_token,
    hash_token,
)
from app.core.telemetry import trace_span, trace_buffer, redact_sensitive_value
from app.core.metrics import enterprise_metrics
from app.models.organization import Organization
from app.models.user import User
from app.models.agent import InfrastructureAgent
from app.models.phase10 import (
    IdentityProviderConfig,
    UserIdentityMapping,
    UserSession,
    SecurityAuditEvent,
    AgentCertificate,
)
from app.services.security.sso_service import SsoService
from app.services.security.session_service import SessionService, SecurityAuditService
from app.services.infrastructure.mtls_ca import AgentCA
from scripts.validate_postgres_backup import BackupIntegrityValidator
from scripts.generate_sbom import generate_cyclonedx_sbom, generate_spdx_sbom


# ------------------------------------------------------------------------------
# 1. Enterprise SSO & PKCE Scenarios
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_01_pkce_generation_and_validation():
    """Scenario 1: Generates RFC 7636 PKCE code_verifier and S256 code_challenge."""
    verifier, challenge = SsoService.generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) > 20
    assert "=" not in challenge  # Base64URL without padding

    import base64
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    assert challenge == expected


@pytest.mark.asyncio
async def test_02_sso_authorization_url_generation():
    """Scenario 2: Generates complete OIDC authorization redirect URL with state and PKCE challenge."""
    org_id = uuid.uuid4()
    provider = IdentityProviderConfig(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Okta Enterprise",
        idp_type="oidc",
        issuer_url="https://auth.example.com",
        client_id="autoheal-client-id-01",
        client_secret_encrypted="encrypted-secret",
    )
    url = SsoService.build_authorization_url(
        provider=provider,
        redirect_uri="https://app.autoheal.dev/auth/callback",
        state="crypto-secure-state-token",
        code_challenge="mock-pkce-challenge",
    )
    assert url.startswith("https://auth.example.com/protocol/openid-connect/auth?")
    assert "client_id=autoheal-client-id-01" in url
    assert "code_challenge=mock-pkce-challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=crypto-secure-state-token" in url


@pytest.mark.asyncio
async def test_03_mock_oidc_exchange():
    """Scenario 3: Simulates hermetic mock OIDC token exchange without external network requests."""
    provider = IdentityProviderConfig(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Test IdP",
        issuer_url="https://test-idp.example.com",
        client_id="test-client-1",
        client_secret_encrypted="enc",
    )
    verifier, challenge = SsoService.generate_pkce_pair()
    code = "mock_code:sub-usr-999:engineer@enterprise.io:Platform-Engineers,DevOps"
    claims = SsoService.simulate_mock_idp_exchange(provider, code, verifier)

    assert claims["iss"] == "https://test-idp.example.com"
    assert claims["sub"] == "sub-usr-999"
    assert claims["email"] == "engineer@enterprise.io"
    assert "Platform-Engineers" in claims["groups"]


@pytest.mark.asyncio
async def test_04_jit_user_provisioning_and_role_mapping(db_session: AsyncSession, seed_data: dict):
    """Scenario 4: JIT (Just-In-Time) provisions new user account with claim-based role mapping."""
    org = seed_data["org_a"]
    provider = IdentityProviderConfig(
        organization_id=org.id,
        name="Corporate Azure AD",
        idp_type="oidc",
        issuer_url="https://login.microsoftonline.com/tenant-1",
        client_id="ms-client-id",
        client_secret_encrypted=encrypt_secret("ms-secret"),
        role_mapping_json={"admin": ["Cloud-Admins"], "operator": ["SRE-Team"], "viewer": ["Employees"]},
        allowed_domains=["enterprise.io"],
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)

    verifier, _ = SsoService.generate_pkce_pair()
    code = "mock_code:sub-new-1:devops-lead@enterprise.io:Cloud-Admins"

    user, access_token, refresh_token, session_id = await SsoService.process_sso_callback(
        db=db_session,
        provider=provider,
        code=code,
        code_verifier=verifier,
        redirect_uri="https://app.autoheal.dev/callback",
    )

    assert user.email == "devops-lead@enterprise.io"
    assert user.organization_id == org.id
    assert user.role == "admin"
    assert access_token is not None
    assert refresh_token is not None
    assert session_id is not None

    stmt = select(UserIdentityMapping).where(UserIdentityMapping.user_id == user.id)
    res = await db_session.execute(stmt)
    mapping = res.scalars().first()
    assert mapping is not None
    assert mapping.external_subject_id == "sub-new-1"


@pytest.mark.asyncio
async def test_05_cross_tenant_identity_takeover_prevention(db_session: AsyncSession, seed_data: dict):
    """Scenario 5: Prevents cross-tenant identity injection when email exists in another organization."""
    org_a = seed_data["org_a"]
    org_b = seed_data["org_b"]

    existing_user = User(
        email="victim@company.com",
        hashed_password="hash",
        full_name="Victim User",
        organization_id=org_b.id,
        role="admin",
        is_active=True,
    )
    db_session.add(existing_user)

    # Provider belonging to org_a
    provider = IdentityProviderConfig(
        organization_id=org_a.id,
        name="Attacker Configured IdP",
        idp_type="oidc",
        issuer_url="https://attacker-idp.example.com",
        client_id="attacker-client",
        client_secret_encrypted=encrypt_secret("sec"),
        allowed_domains=["company.com"],
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()

    verifier, _ = SsoService.generate_pkce_pair()
    code = "mock_code:sub-takeover:victim@company.com:Admins"

    with pytest.raises(ValueError, match="Account belongs to a different organization"):
        await SsoService.process_sso_callback(
            db=db_session,
            provider=provider,
            code=code,
            code_verifier=verifier,
            redirect_uri="https://app.autoheal.dev/callback",
        )

    stmt_audit = select(SecurityAuditEvent).where(
        SecurityAuditEvent.organization_id == org_a.id,
        SecurityAuditEvent.event_type == "cross_tenant_sso_takeover_attempt",
    )
    res_audit = await db_session.execute(stmt_audit)
    audit_evt = res_audit.scalars().first()
    assert audit_evt is not None
    assert audit_evt.severity == "CRITICAL"


@pytest.mark.asyncio
async def test_06_sso_domain_restriction_enforcement(db_session: AsyncSession, seed_data: dict):
    """Scenario 6: Rejects SSO login if user email domain is not in provider allowed_domains."""
    org = seed_data["org_a"]
    provider = IdentityProviderConfig(
        organization_id=org.id,
        name="Corporate SSO Restricted",
        idp_type="oidc",
        issuer_url="https://auth.company.com",
        client_id="client-01",
        client_secret_encrypted=encrypt_secret("sec"),
        allowed_domains=["allowed-corp.com"],
        is_active=True,
    )
    db_session.add(provider)
    await db_session.commit()

    verifier, _ = SsoService.generate_pkce_pair()
    code = "mock_code:sub-ext:outsider@unauthorized-domain.com:Users"

    with pytest.raises(ValueError, match="is not authorized for SSO"):
        await SsoService.process_sso_callback(
            db=db_session,
            provider=provider,
            code=code,
            code_verifier=verifier,
            redirect_uri="https://app.autoheal.dev/callback",
        )


@pytest.mark.asyncio
async def test_07_client_secret_encryption_at_rest():
    """Scenario 7: Encrypts client secrets at rest using AES/Fernet derived key."""
    raw = "super-secret-oauth-client-credential-xyz123"
    enc = encrypt_secret(raw)
    assert enc != raw
    assert "xyz123" not in enc

    decrypted = decrypt_secret(enc)
    assert decrypted == raw


@pytest.mark.asyncio
async def test_08_masked_secret_display():
    """Scenario 8: Masks secrets safely for API responses."""
    secret = "my-secret-token-abcdef1234"
    masked = mask_secret(secret, visible_tail=4)
    assert masked.endswith("1234")
    assert "abcdef" not in masked
    assert "•" in masked


# ------------------------------------------------------------------------------
# 2. Session Security & Replay Attack Defense
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_09_user_session_creation(db_session: AsyncSession, seed_data: dict):
    """Scenario 9: Creates an active UserSession with SHA-256 token hash and expiration."""
    org = seed_data["org_a"]
    user = User(
        email=f"usr-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        full_name="Session User",
        organization_id=org.id,
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    family_id = uuid.uuid4().hex
    session, raw_token = await SessionService.create_session(
        db=db_session,
        user_id=user.id,
        organization_id=org.id,
        family_id=family_id,
        ip_address="192.0.2.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0",
    )
    assert session.is_active is True
    assert session.family_id == family_id
    assert session.device_name == "Chrome on Windows"
    assert session.session_token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_10_user_session_listing(db_session: AsyncSession, seed_data: dict):
    """Scenario 10: Lists active sessions for a user, indicating current session."""
    org = seed_data["org_a"]
    user = User(
        email=f"usr-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        full_name="Listing User",
        organization_id=org.id,
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    sess1, tok1 = await SessionService.create_session(db_session, user.id, org.id, family_id="fam-1")
    sess2, tok2 = await SessionService.create_session(db_session, user.id, org.id, family_id="fam-2")

    sessions = await SessionService.list_active_sessions(db_session, org.id, user.id, current_session_id=sess1.id)
    assert len(sessions) >= 2
    curr = [s for s in sessions if s["id"] == sess1.id][0]
    other = [s for s in sessions if s["id"] == sess2.id][0]
    assert curr["is_current"] is True
    assert other["is_current"] is False


@pytest.mark.asyncio
async def test_11_single_session_revocation(db_session: AsyncSession, seed_data: dict):
    """Scenario 11: Revoking a session deactivates it and logs an audit event."""
    org = seed_data["org_a"]
    user = User(
        email=f"usr-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        full_name="Revoke User",
        organization_id=org.id,
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    sess, tok = await SessionService.create_session(db_session, user.id, org.id, family_id="fam-rev")
    success = await SessionService.revoke_session(
        db_session,
        organization_id=org.id,
        session_id=sess.id,
        reason="Device lost",
    )
    assert success is True

    validated = await SessionService.validate_session(db_session, tok)
    assert validated is None


@pytest.mark.asyncio
async def test_12_revoke_all_sessions(db_session: AsyncSession, seed_data: dict):
    """Scenario 12: Revoking all sessions terminates remote devices while preserving current."""
    org = seed_data["org_a"]
    user = User(
        email=f"usr-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        full_name="RevokeAll User",
        organization_id=org.id,
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    s1, t1 = await SessionService.create_session(db_session, user.id, org.id, family_id="fam-1")
    s2, t2 = await SessionService.create_session(db_session, user.id, org.id, family_id="fam-2")
    s3, t3 = await SessionService.create_session(db_session, user.id, org.id, family_id="fam-3")

    revoked_count = await SessionService.revoke_all_sessions(
        db_session,
        organization_id=org.id,
        user_id=user.id,
        keep_session_id=s1.id,
    )
    assert revoked_count == 2
    assert (await SessionService.validate_session(db_session, t1)) is not None
    assert (await SessionService.validate_session(db_session, t2)) is None
    assert (await SessionService.validate_session(db_session, t3)) is None


@pytest.mark.asyncio
async def test_13_token_family_replay_detection(db_session: AsyncSession, seed_data: dict):
    """Scenario 13: Replay attack triggers full-family revocation and CRITICAL audit event."""
    org = seed_data["org_a"]
    user = User(
        email=f"usr-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hash",
        full_name="Replay User",
        organization_id=org.id,
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    shared_family = "fam-replay-target-99"
    s1, t1 = await SessionService.create_session(db_session, user.id, org.id, family_id=shared_family)
    s2, t2 = await SessionService.create_session(db_session, user.id, org.id, family_id=shared_family)

    await SessionService.handle_family_replay(
        db=db_session,
        organization_id=org.id,
        user_id=user.id,
        family_id=shared_family,
        detected_ip="203.0.113.88",
    )

    assert (await SessionService.validate_session(db_session, t1)) is None
    assert (await SessionService.validate_session(db_session, t2)) is None

    events = await SecurityAuditService.list_events(db_session, org.id, severity="CRITICAL")
    replay_evts = [e for e in events if e.event_type == "token_replay_detected"]
    assert len(replay_evts) > 0
    assert replay_evts[0].ip_address == "203.0.113.88"


# ------------------------------------------------------------------------------
# 3. Infrastructure Agent Mutual TLS (mTLS) & PKI Scenarios
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_14_agent_ca_generation(seed_data: dict):
    """Scenario 14: Generates dedicated root Certificate Authority per organization."""
    org = seed_data["org_a"]
    ca_key, ca_cert = AgentCA.get_or_create_org_ca(org.id)
    assert ca_key.key_size == 2048
    assert f"AutoHeal-Org-{str(org.id)[:8]}" in ca_cert.subject.rfc4514_string()


@pytest.mark.asyncio
async def test_15_agent_client_certificate_issuance(db_session: AsyncSession, seed_data: dict):
    """Scenario 15: Issues X.509 client certificate for agent with client_auth EKU."""
    org = seed_data["org_a"]
    agent = InfrastructureAgent(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name="k8s-us-east-worker",
        hostname="worker-node-01",
        ip_address="10.0.12.5",
        public_key_fingerprint="sha256:testfingerprint15",
        status="active",
        secret_key_hash="hash",
    )
    db_session.add(agent)
    await db_session.flush()

    cert_record, cert_pem, key_pem, ca_pem = await AgentCA.issue_agent_certificate(
        db=db_session,
        organization_id=org.id,
        agent_id=agent.id,
        common_name="agent-worker-01",
        valid_days=90,
    )

    assert cert_record.agent_id == agent.id
    assert cert_record.is_revoked is False
    assert "-----BEGIN CERTIFICATE-----" in cert_pem
    assert "-----BEGIN PRIVATE KEY-----" in key_pem
    assert "-----BEGIN CERTIFICATE-----" in ca_pem


@pytest.mark.asyncio
async def test_16_valid_agent_certificate_verification(db_session: AsyncSession, seed_data: dict):
    """Scenario 16: Cryptographically verifies client certificate against Org CA."""
    org = seed_data["org_a"]
    agent = InfrastructureAgent(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name="k8s-agent-verify",
        hostname="worker-node-16",
        ip_address="10.0.12.6",
        public_key_fingerprint="sha256:testfingerprint16",
        status="active",
    )
    db_session.add(agent)
    await db_session.flush()

    cert_rec, cert_pem, key_pem, ca_pem = await AgentCA.issue_agent_certificate(
        db=db_session,
        organization_id=org.id,
        agent_id=agent.id,
    )

    result = await AgentCA.verify_agent_certificate(
        db=db_session,
        organization_id=org.id,
        cert_pem=cert_pem,
    )
    assert result["valid"] is True
    assert result["agent_id"] == str(agent.id)


@pytest.mark.asyncio
async def test_17_expired_agent_certificate_rejection(db_session: AsyncSession, seed_data: dict):
    """Scenario 17: Rejects expired agent client certificates."""
    org = seed_data["org_a"]
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import serialization

    ca_key, ca_cert = AgentCA.get_or_create_org_ca(org.id)
    expired_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "expired-agent")]))
        .issuer_name(ca_cert.subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=40))
        .not_valid_after(datetime.now(timezone.utc) - timedelta(days=10))
        .sign(ca_key, hashes.SHA256())
    )
    expired_pem = expired_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    res = await AgentCA.verify_agent_certificate(db_session, org.id, expired_pem)
    assert res["valid"] is False
    assert "expired" in res["reason"].lower()


@pytest.mark.asyncio
async def test_18_revoked_agent_certificate_rejection(db_session: AsyncSession, seed_data: dict):
    """Scenario 18: Rejects revoked client certificates."""
    org = seed_data["org_a"]
    agent = InfrastructureAgent(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name="k8s-revoke-test",
        hostname="worker-node-18",
        ip_address="10.0.12.7",
        public_key_fingerprint="sha256:testfingerprint18",
        status="active",
    )
    db_session.add(agent)
    await db_session.flush()

    cert_rec, cert_pem, _, _ = await AgentCA.issue_agent_certificate(
        db=db_session, organization_id=org.id, agent_id=agent.id
    )

    success = await AgentCA.revoke_certificate(
        db=db_session,
        organization_id=org.id,
        agent_id=agent.id,
        reason="Compromised host key",
    )
    assert success is True

    res = await AgentCA.verify_agent_certificate(db_session, org.id, cert_pem)
    assert res["valid"] is False
    assert "revoked" in res["reason"].lower()


@pytest.mark.asyncio
async def test_19_live_mtls_handshake_verification(db_session: AsyncSession, seed_data: dict):
    """Scenario 19: Executes live mutual TLS handshake test using MemoryBIO with CERT_REQUIRED."""
    org = seed_data["org_a"]
    agent = InfrastructureAgent(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        name="k8s-handshake-node",
        hostname="worker-node-19",
        ip_address="10.0.12.8",
        public_key_fingerprint="sha256:testfingerprint19",
        status="active",
    )
    db_session.add(agent)
    await db_session.flush()

    cert_rec, cert_pem, key_pem, ca_pem = await AgentCA.issue_agent_certificate(
        db=db_session,
        organization_id=org.id,
        agent_id=agent.id,
        common_name="agent-node-handshake",
    )

    res = AgentCA.test_live_mtls_handshake(
        organization_id=org.id,
        client_cert_pem=cert_pem,
        client_key_pem=key_pem,
    )
    assert res["handshake_success"] is True
    assert res["peer_certificate"] is not None
    assert "TLS" in res["protocol_version"]


# ------------------------------------------------------------------------------
# 4. OpenTelemetry Tracing & Attribute Redaction
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_20_opentelemetry_span_creation():
    """Scenario 20: Wraps execution with trace_span and records trace in circular buffer."""
    with trace_span("database.query.recovery_policy", service="postgresql-asyncpg", attributes={"db.statement": "SELECT * FROM policies"}):
        time.sleep(0.005)

    recent = trace_buffer.get_recent(limit=10)
    matched = [t for t in recent if t["name"] == "database.query.recovery_policy"]
    assert len(matched) > 0
    assert matched[0]["status"] == "OK"
    assert matched[0]["duration_ms"] > 0


@pytest.mark.asyncio
async def test_21_opentelemetry_attribute_redaction():
    """Scenario 21: Redacts sensitive attributes from distributed spans."""
    sanitized = redact_sensitive_value("Authorization", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret")
    assert sanitized == "[REDACTED]"

    sanitized_pwd = redact_sensitive_value("db_password", "super-secret-pass-999")
    assert sanitized_pwd == "[REDACTED]"

    sanitized_tok = redact_sensitive_value("webhook_token", "whsec_abcdef123456")
    assert sanitized_tok == "[REDACTED]"

    normal = redact_sensitive_value("http.method", "GET")
    assert normal == "GET"


# ------------------------------------------------------------------------------
# 5. Observability & Prometheus Metrics
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_22_prometheus_metrics_generation():
    """Scenario 22: Records and renders Prometheus text metrics exposition."""
    enterprise_metrics.record_request("GET", "/api/v1/health", 200, 0.005)
    enterprise_metrics.record_mtls_handshake("org-test-1", True)
    enterprise_metrics.record_recovery_run("simulated", "success")

    text = enterprise_metrics.render_prometheus_text({"pool_size": 15, "checked_out": 2, "overflow": 0})
    assert "autoheal_up 1" in text
    assert 'autoheal_http_requests_total{method="GET",endpoint="/api/v1/health",status="200"}' in text
    assert 'autoheal_agent_mtls_handshakes_total{org="org-test-1",status="success"}' in text
    assert 'autoheal_recovery_executions_total{mode="simulated",status="success"}' in text


@pytest.mark.asyncio
async def test_23_observability_summary_stats():
    """Scenario 23: Calculates high-level telemetry and SLA stats for dashboard."""
    enterprise_metrics.record_request("POST", "/api/v1/recoveries/execute", 200, 0.050)
    stats = enterprise_metrics.get_summary_stats({"pool_size": 20, "checked_out": 3, "overflow": 0})
    assert stats["total_requests"] > 0
    assert "error_rate_pct" in stats
    assert stats["db_pool"]["pool_size"] == 20


# ------------------------------------------------------------------------------
# 6. Multi-Tenant Organization Isolation Scenarios
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_24_multi_tenant_sso_isolation(db_session: AsyncSession, seed_data: dict):
    """Scenario 24: Org A cannot view Org B SSO identity providers."""
    org_a = seed_data["org_a"]
    org_b = seed_data["org_b"]

    idp_b = IdentityProviderConfig(
        organization_id=org_b.id,
        name="Tenant B IdP",
        issuer_url="https://auth.b.com",
        client_id="b-client",
        client_secret_encrypted="enc",
    )
    db_session.add(idp_b)
    await db_session.commit()

    stmt = select(IdentityProviderConfig).where(IdentityProviderConfig.organization_id == org_a.id)
    res = await db_session.execute(stmt)
    providers_a = res.scalars().all()
    assert idp_b.id not in [p.id for p in providers_a]


@pytest.mark.asyncio
async def test_25_multi_tenant_session_isolation(db_session: AsyncSession, seed_data: dict):
    """Scenario 25: Org A cannot revoke Org B user sessions."""
    org_a = seed_data["org_a"]
    org_b = seed_data["org_b"]

    user_b = seed_data["user_b"]
    sess_b, tok_b = await SessionService.create_session(db_session, user_b.id, org_b.id, "fam-b")

    success = await SessionService.revoke_session(
        db_session,
        organization_id=org_a.id,
        session_id=sess_b.id,
    )
    assert success is False
    assert (await SessionService.validate_session(db_session, tok_b)) is not None


@pytest.mark.asyncio
async def test_26_multi_tenant_agent_cert_isolation(db_session: AsyncSession, seed_data: dict):
    """Scenario 26: Org A cannot revoke or verify Org B agent certificates."""
    org_a = seed_data["org_a"]
    org_b = seed_data["org_b"]

    agent_b = InfrastructureAgent(
        id=str(uuid.uuid4()),
        organization_id=org_b.id,
        name="agent-b",
        hostname="worker-node-org-b",
        ip_address="10.0.12.9",
        public_key_fingerprint="sha256:testfingerprint26",
        status="active",
    )
    db_session.add(agent_b)
    await db_session.flush()

    cert_b, cert_pem_b, _, _ = await AgentCA.issue_agent_certificate(db_session, org_b.id, agent_b.id)

    revoked = await AgentCA.revoke_certificate(db_session, org_a.id, agent_b.id)
    assert revoked is False

    verified = await AgentCA.verify_agent_certificate(db_session, org_a.id, cert_pem_b)
    assert verified["valid"] is False


# ------------------------------------------------------------------------------
# 7. Database Hardening, Backup Validation & Supply-Chain Security
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_27_database_pool_hardening_configuration():
    """Scenario 27: Database connection engine pool arguments enforce pool_pre_ping and recycle."""
    from app.database import get_engine_args
    args = get_engine_args("postgresql+asyncpg://user:pass@localhost:5432/autoheal")
    assert args.get("pool_pre_ping") is True
    assert args.get("pool_recycle") is not None
    assert args.get("pool_timeout") is not None


@pytest.mark.asyncio
async def test_28_automated_backup_restore_pipeline():
    """Scenario 28: Validates end-to-end backup, encryption, decryption checksum, restore, and RTO/RPO."""
    validator = BackupIntegrityValidator()
    result = await validator.run_validation()
    assert result["status"] == "PASSED"
    assert result["metrics"]["rto_sla_met"] is True
    assert result["metrics"]["rpo_sla_met"] is True
    assert result["metrics"]["measured_rto_seconds"] < 900.0


@pytest.mark.asyncio
async def test_29_sbom_cyclonedx_and_spdx_generation():
    """Scenario 29: Verifies CycloneDX 1.5 and SPDX 2.3 SBOM generation logic."""
    sample_components = [
        {"name": "fastapi", "version": "0.115.0", "purl": "pkg:pypi/fastapi@0.115.0"},
        {"name": "cryptography", "version": "43.0.0", "purl": "pkg:pypi/cryptography@43.0.0"},
    ]
    cdx = generate_cyclonedx_sbom(sample_components)
    assert cdx["bomFormat"] == "CycloneDX"
    assert cdx["specVersion"] == "1.5"
    assert len(cdx["components"]) == 2

    spdx = generate_spdx_sbom(sample_components)
    assert spdx["spdxVersion"] == "SPDX-2.3"
    assert len(spdx["packages"]) == 2


def test_30_rbac_sso_provider_management(client: TestClient, seed_data: dict):
    """Scenario 30: RBAC enforcement on SSO provider creation (Admin required, Viewer forbidden 403)."""
    user_a = seed_data["user_a"]

    # 1. Admin succeeds
    user_a.role = "admin"
    payload = {
        "name": "Admin Configured IdP",
        "idp_type": "oidc",
        "issuer_url": "https://auth.admin.com",
        "client_id": "client-admin",
        "client_secret": "my-admin-secret",
    }
    res_admin = client.post("/api/v1/auth/sso/providers", json=payload)
    assert res_admin.status_code == 201

    # 2. Viewer gets 403 Forbidden
    user_a.role = "viewer"
    res_viewer = client.post("/api/v1/auth/sso/providers", json=payload)
    assert res_viewer.status_code == 403

    user_a.role = "operator"  # Restore role
