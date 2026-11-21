"""
AutoHeal DevOps — Canary Release & Deployment Intelligence API Router
Evaluates progressive rollout stages, baseline vs canary metrics, regression detection,
and advisory rollback recommendations (simulated/advisory only).
"""

from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from app.api.deps import DatabaseDep, OrgDep, RequireRole, UserDep
from app.models.enterprise import ReleaseEvaluation, ReleaseEvaluationMetric
from app.models.service import Service
from app.schemas.enterprise import (
    CanaryEvaluationRequest,
    ReleaseEvaluationResponse,
    ReleaseEvaluationMetricResponse,
)
from app.services.enterprise.release_evaluator import CanaryReleaseEvaluator

router = APIRouter(prefix="/releases", tags=["Release Intelligence"])
evaluator = CanaryReleaseEvaluator()


def serialize_evaluation(ev: ReleaseEvaluation) -> ReleaseEvaluationResponse:
    metrics = [
        ReleaseEvaluationMetricResponse(
            metric_name=m.metric_name,
            baseline_value=m.baseline_value,
            canary_value=m.canary_value,
            delta=m.delta,
            threshold_value=m.threshold_value,
            status=m.status,  # pass, warning, breach
            evaluated_at=m.evaluated_at.isoformat() if m.evaluated_at else "",
        )
        for m in (ev.metrics or [])
    ]

    service_name = ev.service.name if ev.service else ev.service_id

    return ReleaseEvaluationResponse(
        id=str(ev.id),
        organization_id=str(ev.organization_id),
        service_id=ev.service_id,
        service_name=service_name,
        release_tag=ev.release_tag,
        stage=ev.stage,
        status=ev.status,
        traffic_percentage=ev.traffic_percentage,
        observation_window_minutes=ev.observation_window_minutes,
        sample_count=ev.sample_count,
        regression_detected=ev.regression_detected,
        recommendation=ev.recommendation,  # proceed, pause, rollback_recommended
        explanation=ev.explanation,
        metrics=metrics,
        evaluated_at=ev.evaluated_at.isoformat() if ev.evaluated_at else "",
        created_at=ev.created_at.isoformat() if ev.created_at else "",
    )


@router.get("/evaluations", response_model=List[ReleaseEvaluationResponse], summary="List release evaluations")
async def list_evaluations(
    org: OrgDep,
    db: DatabaseDep,
    service_id: Optional[str] = None,
    limit: int = Query(default=30, le=100),
) -> List[ReleaseEvaluationResponse]:
    """Lists canary evaluations and progressive rollout telemetry assessments."""
    q = (
        select(ReleaseEvaluation)
        .options(selectinload(ReleaseEvaluation.service), selectinload(ReleaseEvaluation.metrics))
        .where(ReleaseEvaluation.organization_id == org.id)
    )
    if service_id:
        q = q.where(ReleaseEvaluation.service_id == service_id)

    q = q.order_by(desc(ReleaseEvaluation.evaluated_at)).limit(limit)
    res = await db.execute(q)
    return [serialize_evaluation(ev) for ev in res.scalars().all()]


@router.post("/evaluate-canary", response_model=ReleaseEvaluationResponse, summary="Evaluate canary rollout", status_code=status.HTTP_201_CREATED)
async def evaluate_canary(
    payload: CanaryEvaluationRequest,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> ReleaseEvaluationResponse:
    """
    Evaluates canary telemetry against baseline performance.
    Advisory only; never executes production rollbacks. Requires operator or admin role.
    """
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    # Validate service
    svc_q = select(Service).where(
        and_(
            Service.organization_id == org.id,
            Service.id == payload.service_id,
        )
    )
    svc_res = await db.execute(svc_q)
    service = svc_res.scalars().first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")

    try:
        evaluation = await evaluator.evaluate_canary(
            db=db,
            organization_id=org.id,
            service_id=payload.service_id,
            release_tag=payload.release_tag,
            traffic_percentage=payload.traffic_percentage,
            observation_window_minutes=payload.observation_window_minutes,
            custom_thresholds=payload.thresholds,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Eagerly load service and metrics for response
    eval_q = (
        select(ReleaseEvaluation)
        .options(selectinload(ReleaseEvaluation.service), selectinload(ReleaseEvaluation.metrics))
        .where(ReleaseEvaluation.id == evaluation.id)
    )
    eval_res = await db.execute(eval_q)
    full_eval = eval_res.scalars().first()
    return serialize_evaluation(full_eval or evaluation)


@router.get("/evaluations/{evaluation_id}", response_model=ReleaseEvaluationResponse, summary="Get release evaluation detail")
async def get_evaluation(
    evaluation_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> ReleaseEvaluationResponse:
    """Retrieves specific canary release evaluation and metric delta breakdown."""
    try:
        eid = uuid.UUID(evaluation_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid evaluation ID.")

    q = (
        select(ReleaseEvaluation)
        .options(selectinload(ReleaseEvaluation.service), selectinload(ReleaseEvaluation.metrics))
        .where(
            and_(
                ReleaseEvaluation.organization_id == org.id,
                ReleaseEvaluation.id == eid,
            )
        )
    )
    res = await db.execute(q)
    evaluation = res.scalars().first()
    if not evaluation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation record not found.")

    return serialize_evaluation(evaluation)
