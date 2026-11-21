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
