"""
AutoHeal DevOps — Recovery Policy Management Router
Supports policy configuration, governance inspection, and dry-run policy evaluation.
"""

from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DatabaseDep, OrgDep, RequireOperatorDep
from app.models.audit import AuditLog
from app.models.service import RecoveryPolicy, Service
from app.schemas.policy import (
    PolicyEvaluationRequest,
    PolicyEvaluationResponse,
    PolicyResponse,
    PolicyUpdateRequest,
)
from app.services.recovery.policy_engine import policy_engine

router = APIRouter(prefix="/policies", tags=["Recovery Policies"])


def format_policy_response(pol: RecoveryPolicy) -> PolicyResponse:
    return PolicyResponse(
        id=str(pol.id),
        service_id=pol.service_id,
        action=pol.action,
        approval_required=pol.approval_required,
        cooldown_seconds=pol.cooldown_seconds,
        max_retries=pol.max_retries,
        is_active=pol.is_active,
    )


@router.get(
    "",
    response_model=List[PolicyResponse],
    summary="List organization recovery policies",
)
async def list_policies(
    org: OrgDep,
    db: DatabaseDep,
) -> List[PolicyResponse]:
    """Returns all active recovery governance policies for services in this organization."""
    stmt = (
        select(RecoveryPolicy)
        .join(Service, RecoveryPolicy.service_id == Service.id)
        .where(Service.organization_id == org.id)
    )
    result = await db.execute(stmt)
    policies = result.scalars().all()
    return [format_policy_response(p) for p in policies]


@router.get(
    "/{service_id}",
    response_model=List[PolicyResponse],
    summary="Get recovery policies for a specific service",
)
async def get_service_policies(
    service_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> List[PolicyResponse]:
    """Retrieves policies defined for a specific service in the caller's organization."""
    svc_res = await db.execute(
        select(Service).where(Service.id == service_id, Service.organization_id == org.id)
    )
    if not svc_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_id}' was not found in this organization.",
        )

    stmt = select(RecoveryPolicy).where(RecoveryPolicy.service_id == service_id)
    result = await db.execute(stmt)
    return [format_policy_response(p) for p in result.scalars().all()]


@router.post(
    "/{service_id}",
    response_model=PolicyResponse,
    status_code=status.HTTP_200_OK,
    summary="Create or update recovery policy for a service",
)
async def upsert_policy(
    service_id: str,
    payload: PolicyUpdateRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
    action: str = "restart_service",
) -> PolicyResponse:
    """Updates or creates a governance policy for a service and action."""
    svc_res = await db.execute(
        select(Service).where(Service.id == service_id, Service.organization_id == org.id)
    )
    service = svc_res.scalar_one_or_none()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_id}' was not found in this organization.",
        )

    stmt = select(RecoveryPolicy).where(
        RecoveryPolicy.service_id == service_id,
        RecoveryPolicy.action == action,
    )
    result = await db.execute(stmt)
    policy = result.scalar_one_or_none()

    if not policy:
        policy = RecoveryPolicy(
            id=uuid.uuid4(),
            service_id=service_id,
            action=action,
            approval_required=payload.approval_required if payload.approval_required is not None else True,
            cooldown_seconds=payload.cooldown_seconds if payload.cooldown_seconds is not None else 900,
            max_retries=payload.max_retries if payload.max_retries is not None else 3,
            is_active=payload.is_active if payload.is_active is not None else True,
        )
        db.add(policy)
    else:
        if payload.approval_required is not None:
            policy.approval_required = payload.approval_required
        if payload.cooldown_seconds is not None:
            policy.cooldown_seconds = payload.cooldown_seconds
        if payload.max_retries is not None:
            policy.max_retries = payload.max_retries
        if payload.is_active is not None:
            policy.is_active = payload.is_active

    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="policy_updated",
        resource_type="recovery_policy",
        resource_id=str(policy.id),
        details=f"Policy for '{service.name}' action '{action}' updated by {current_user.email}.",
    ))
    await db.commit()
    await db.refresh(policy)

    return format_policy_response(policy)


@router.post(
    "/evaluate/check",
    response_model=PolicyEvaluationResponse,
    summary="Dry-run recovery policy evaluation",
)
async def evaluate_policy_dry_run(
    payload: PolicyEvaluationRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> PolicyEvaluationResponse:
    """Performs dry-run policy evaluation against governance constraints."""
    result = await policy_engine.evaluate_policy(
        db=db,
        organization_id=org.id,
        service_id=payload.service_id,
        action=payload.action,
        operator_role=current_user.role,
        agent_id=payload.agent_id,
    )

    return PolicyEvaluationResponse(
        allowed=result.allowed,
        requires_approval=result.requires_approval,
        reason=result.reason,
        cooldown_remaining_seconds=result.cooldown_remaining_seconds,
        retry_count=result.retry_count,
        max_retries=result.max_retries,
    )
