"""
AutoHeal DevOps — Infrastructure Agents Router
Manages agent registration, heartbeats, status queries, and credentials revocation.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import secrets
import time
from typing import List, Optional
import uuid

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import desc, select

from app.api.deps import DatabaseDep, OrgDep, RequireOperatorDep
from app.models.agent import InfrastructureAgent
from app.models.audit import AuditLog
from app.schemas.agent import (
    AgentHeartbeatRequest,
    AgentMessageResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentResponse,
)
from app.models.phase10 import AgentCertificate
from app.schemas.phase10 import (
    AgentCertIssueRequest,
    AgentCertResponse,
    AgentCertBundleResponse,
    AgentCertRevokeRequest,
)
from app.services.infrastructure.mtls_ca import AgentCA
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Infrastructure Agents"])

_SEEN_NONCES: set[str] = set()


def format_agent_response(agent: InfrastructureAgent) -> AgentResponse:
    """Formats InfrastructureAgent DB model into standardized API schema."""
    last_hb_str = agent.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S UTC") if agent.last_heartbeat else "Never"
    created_str = agent.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if agent.created_at else "Unknown"

    return AgentResponse(
        id=agent.id,
        organization_id=str(agent.organization_id),
        name=agent.name,
        hostname=agent.hostname,
        ip_address=agent.ip_address,
        environment=agent.environment,
        status=agent.status,
        version=agent.version,
        capabilities=agent.capabilities,
        public_key_fingerprint=agent.public_key_fingerprint,
        last_heartbeat=last_hb_str,
        created_at=created_str,
    )


@router.get(
    "",
    response_model=List[AgentResponse],
    summary="List organization infrastructure agents",
)
async def list_agents(
    org: OrgDep,
    db: DatabaseDep,
) -> List[AgentResponse]:
    """Returns all infrastructure agents registered to the caller's organization."""
    stmt = (
        select(InfrastructureAgent)
        .where(InfrastructureAgent.organization_id == org.id)
        .order_by(desc(InfrastructureAgent.last_heartbeat))
    )
    result = await db.execute(stmt)
    agents = result.scalars().all()
    return [format_agent_response(a) for a in agents]


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new infrastructure agent",
)
async def register_agent(
    payload: AgentRegisterRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> AgentRegisterResponse:
    """
    Registers an infrastructure agent under the caller's organization.
    Generates a secure signing secret and returns credentials.
    """
    agent_id = f"agent-{uuid.uuid4().hex[:12]}"
    raw_secret = secrets.token_hex(32)
    secret_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()

    pubkey_fp = payload.public_key_fingerprint or hashlib.sha256(f"{agent_id}:{payload.hostname}".encode()).hexdigest()

    now = datetime.now(timezone.utc)
    agent = InfrastructureAgent(
        id=agent_id,
        organization_id=org.id,
        name=payload.name,
        hostname=payload.hostname,
        ip_address=payload.ip_address,
        environment=payload.environment,
        status="online",
        version="1.0.0",
        capabilities_json=json.dumps(payload.capabilities),
        public_key_fingerprint=pubkey_fp,
        secret_key_hash=secret_hash,
        last_heartbeat=now,
    )
    db.add(agent)

    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="agent_registered",
        resource_type="infrastructure_agent",
        resource_id=agent_id,
        details=f"Agent '{agent.name}' ({agent.hostname}) registered by {current_user.email} in environment {agent.environment}.",
    ))
    await db.commit()
    await db.refresh(agent)

    # Emit real-time SSE event
    await event_broadcaster.broadcast(org.id, "agent_registered", {
        "id": agent.id,
        "name": agent.name,
        "hostname": agent.hostname,
        "status": agent.status,
    })

    return AgentRegisterResponse(
        agent=format_agent_response(agent),
        agent_secret=raw_secret,
        secret_key=raw_secret,
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get infrastructure agent details",
)
async def get_agent(
    agent_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> AgentResponse:
    """Retrieves single infrastructure agent scoped to caller's organization."""
    stmt = select(InfrastructureAgent).where(
        InfrastructureAgent.id == agent_id,
        InfrastructureAgent.organization_id == org.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Infrastructure agent '{agent_id}' was not found in this organization.",
        )

    return format_agent_response(agent)


@router.post(
    "/{agent_id}/heartbeat",
    response_model=AgentMessageResponse,
    summary="Record infrastructure agent heartbeat",
)
async def record_heartbeat(
    agent_id: str,
    org: OrgDep,
    db: DatabaseDep,
    payload: Optional[AgentHeartbeatRequest] = None,
    x_agent_timestamp: Optional[str] = Header(None, alias="X-Agent-Timestamp"),
    x_agent_nonce: Optional[str] = Header(None, alias="X-Agent-Nonce"),
    x_agent_signature: Optional[str] = Header(None, alias="X-Agent-Signature"),
) -> AgentMessageResponse:
    """
    Updates agent last heartbeat timestamp and operational state.
    Enforces timestamp clock drift limits (< 300s) and nonce replay prevention.
    """
    if x_agent_timestamp is not None:
        try:
            ts_val = int(x_agent_timestamp)
            now_ts = int(time.time())
            if abs(now_ts - ts_val) > 300:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Timestamp drift exceeds allowable threshold (300s).",
                )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid timestamp format in X-Agent-Timestamp header.",
            )

    if x_agent_nonce is not None:
        if x_agent_nonce in _SEEN_NONCES:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cryptographic nonce already used (replay attack detected).",
            )
        _SEEN_NONCES.add(x_agent_nonce)
        if len(_SEEN_NONCES) > 10000:
            _SEEN_NONCES.clear()

    stmt = select(InfrastructureAgent).where(
        InfrastructureAgent.id == agent_id,
        InfrastructureAgent.organization_id == org.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Infrastructure agent '{agent_id}' was not found in this organization.",
        )

    if agent.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Infrastructure agent '{agent_id}' has been revoked. Access denied.",
        )

    now = datetime.now(timezone.utc)
    agent.last_heartbeat = now
    if payload:
        agent.status = payload.status
    await db.commit()

    return AgentMessageResponse(
        message="Heartbeat recorded successfully.",
        status=agent.status,
    )


@router.post(
    "/{agent_id}/revoke",
    response_model=AgentMessageResponse,
    summary="Revoke infrastructure agent authorization",
)
async def revoke_agent(
    agent_id: str,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> AgentMessageResponse:
    """Revokes credentials for an infrastructure agent."""
    stmt = select(InfrastructureAgent).where(
        InfrastructureAgent.id == agent_id,
        InfrastructureAgent.organization_id == org.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Infrastructure agent '{agent_id}' was not found in this organization.",
        )

    agent.status = "revoked"
    agent.secret_key_hash = None

    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="agent_revoked",
        resource_type="infrastructure_agent",
        resource_id=agent_id,
        details=f"Agent '{agent.name}' ({agent.id}) credentials revoked by {current_user.email}.",
    ))
    await db.commit()

    return AgentMessageResponse(
        message=f"Agent '{agent_id}' authorization successfully revoked.",
        status="revoked",
    )


# ==============================================================================
# Phase 10: Infrastructure Agent Mutual TLS (mTLS) Certificate Endpoints
# ==============================================================================

@router.post(
    "/{agent_id}/cert",
    response_model=AgentCertBundleResponse,
    summary="Issue or rotate infrastructure agent mTLS certificate",
)
async def issue_agent_cert(
    agent_id: str,
    payload: Optional[AgentCertIssueRequest] = None,
    org: OrgDep = None,
    current_user: RequireOperatorDep = None,
    db: DatabaseDep = None,
) -> AgentCertBundleResponse:
    """Issues a new X.509 client certificate for mTLS authentication."""
    stmt = select(InfrastructureAgent).where(
        InfrastructureAgent.id == agent_id,
        InfrastructureAgent.organization_id == org.id,
    )
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Infrastructure agent not found.")

    valid_days = payload.valid_days if payload else 365
    common_name = (payload.common_name if payload else None) or f"{agent.name}-{agent_id[:8]}"

    cert_record, cert_pem, key_pem, ca_pem = await AgentCA.issue_agent_certificate(
        db=db,
        organization_id=org.id,
        agent_id=agent_id,
        common_name=common_name,
        valid_days=valid_days,
    )

    return AgentCertBundleResponse(
        id=cert_record.id,
        organization_id=cert_record.organization_id,
        agent_id=cert_record.agent_id,
        serial_number=cert_record.serial_number,
        fingerprint_sha256=cert_record.fingerprint_sha256,
        subject_dn=cert_record.subject_dn,
        issuer_dn=cert_record.issuer_dn,
        valid_from=cert_record.valid_from,
        valid_to=cert_record.valid_to,
        is_revoked=cert_record.is_revoked,
        revoked_at=cert_record.revoked_at,
        revocation_reason=cert_record.revocation_reason,
        cert_pem=cert_pem,
        private_key_pem=key_pem,
        ca_cert_pem=ca_pem,
        created_at=cert_record.created_at,
    )


@router.get(
    "/{agent_id}/cert",
    response_model=AgentCertResponse,
    summary="Get active mTLS certificate for agent",
)
async def get_agent_cert(
    agent_id: str,
    org: OrgDep = None,
    current_user: RequireOperatorDep = None,
    db: DatabaseDep = None,
) -> AgentCertResponse:
    """Retrieves active certificate metadata for the specified agent."""
    stmt = (
        select(AgentCertificate)
        .where(
            AgentCertificate.agent_id == agent_id,
            AgentCertificate.organization_id == org.id,
            AgentCertificate.is_revoked == False,
        )
        .order_by(desc(AgentCertificate.created_at))
    )
    res = await db.execute(stmt)
    cert = res.scalars().first()
    if not cert:
        raise HTTPException(status_code=404, detail="No active certificate found for agent.")

    return AgentCertResponse.model_validate(cert)


@router.post(
    "/{agent_id}/revoke-cert",
    summary="Revoke active mTLS certificate for agent",
)
async def revoke_agent_cert(
    agent_id: str,
    payload: Optional[AgentCertRevokeRequest] = None,
    org: OrgDep = None,
    current_user: RequireOperatorDep = None,
    db: DatabaseDep = None,
):
    """Revokes active client certificate, immediately invalidating agent mTLS connection."""
    reason = payload.reason if payload else "Operator manual revocation"
    success = await AgentCA.revoke_certificate(
        db=db,
        organization_id=org.id,
        agent_id=agent_id,
        reason=reason,
    )
    if not success:
        raise HTTPException(status_code=404, detail="No active certificate found to revoke.")

    return {"status": "success", "message": "Agent mTLS certificate revoked."}


@router.post(
    "/{agent_id}/verify-mtls",
    summary="Verify agent mTLS certificate and test TLS handshake",
)
async def verify_agent_mtls(
    agent_id: str,
    org: OrgDep = None,
    current_user: RequireOperatorDep = None,
    db: DatabaseDep = None,
):
    """Cryptographically verifies certificate against CA and executes live mTLS handshake test."""
    stmt = (
        select(AgentCertificate)
        .where(
            AgentCertificate.agent_id == agent_id,
            AgentCertificate.organization_id == org.id,
        )
        .order_by(desc(AgentCertificate.created_at))
    )
    res = await db.execute(stmt)
    cert = res.scalars().first()
    if not cert:
        raise HTTPException(status_code=404, detail="No certificate found for agent.")

    verification = await AgentCA.verify_agent_certificate(
        db=db,
        organization_id=org.id,
        cert_pem=cert.cert_pem,
    )
    return {
        "status": "success",
        "is_valid": verification.get("valid", False),
        "details": verification,
    }

