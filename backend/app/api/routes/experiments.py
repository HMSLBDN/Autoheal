"""
AutoHeal DevOps — Phase 14 Experiment & Benchmark Router
Provides multi-tenant APIs to configure, execute, analyze, compare, and report
on deterministic self-healing benchmark experiments.
"""

from datetime import datetime
import io
from typing import List, Literal, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    DatabaseDep,
    OrgDep,
    RequireOperatorDep,
    RequireViewerDep,
    UserDep,
)
from app.models.base import utc_now
from app.models.experiment import Experiment, ExperimentRun
from app.schemas.experiment import (
    ExperimentAnalyticsResponse,
    ExperimentComparisonResponse,
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentRunResponse,
)
from app.services.experiment import (
    ExperimentRunner,
    build_experiment_analytics,
    compare_experiments,
    generate_experiment_json_report,
    generate_experiment_pdf_report,
)

router = APIRouter(prefix="/experiments", tags=["Experiments & Benchmarks"])


def _format_run_response(r: ExperimentRun) -> ExperimentRunResponse:
    return ExperimentRunResponse(
        id=r.id,
        experiment_id=r.experiment_id,
        run_number=r.run_number,
        status=r.status,  # type: ignore
        recovery_enabled=r.recovery_enabled,
        seed=r.seed,
        fault_injected_at=r.fault_injected_at,
        detected_at=r.detected_at,
        recovery_started_at=r.recovery_started_at,
        recovery_completed_at=r.recovery_completed_at,
        health_restored_at=r.health_restored_at,
        detection_latency_ms=r.detection_latency_ms,
        recovery_duration_ms=r.recovery_duration_ms,
        total_outage_duration_ms=r.total_outage_duration_ms,
        recovery_attempted=r.recovery_attempted,
        recovery_verified=r.recovery_verified,
        recovery_success=r.recovery_success,
        is_false_positive=r.is_false_positive,
        safety_compliant=r.safety_compliant,
        escalated=r.escalated,
        incident_id=r.incident_id,
        recovery_action_id=r.recovery_action_id,
        evidence_classification=r.evidence_classification,  # type: ignore
        telemetry_samples=r.telemetry_samples or [],
        execution_log=r.execution_log or [],
        error_message=r.error_message,
        started_at=r.started_at,
        completed_at=r.completed_at,
        created_at=r.created_at,
    )


def _format_experiment_response(exp: Experiment, include_runs: bool = False) -> ExperimentResponse:
    runs_res = None
    runs_count = len(exp.runs) if exp.runs else 0
    if include_runs and exp.runs:
        runs_res = [_format_run_response(r) for r in exp.runs]

    return ExperimentResponse(
        id=exp.id,
        organization_id=exp.organization_id,
        created_by_user_id=exp.created_by_user_id,
        name=exp.name,
        description=exp.description,
        scenario_type=exp.scenario_type,
        execution_mode=exp.execution_mode,
        recovery_enabled=exp.recovery_enabled,
        target_service_id=exp.target_service_id,
        number_of_runs=exp.number_of_runs,
        random_seed=exp.random_seed,
        configuration=exp.configuration or {},
        test_conditions=exp.test_conditions or {},
        status=exp.status,  # type: ignore
        started_at=exp.started_at,
        completed_at=exp.completed_at,
        results_summary=exp.results_summary or {},
        runs_count=runs_count,
        runs=runs_res,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
    )


@router.post(
    "",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new benchmark experiment",
)
async def create_experiment(
    payload: ExperimentCreateRequest,
    user: RequireOperatorDep,
    org: OrgDep,
    db: DatabaseDep,
) -> ExperimentResponse:
    """Configures a reproducible benchmark experiment under strict tenant isolation."""
    exp_id = f"EXP-{uuid.uuid4().hex[:8].upper()}"
    experiment = Experiment(
        id=exp_id,
        organization_id=org.id,
        created_by_user_id=user.id,
        name=payload.name,
        description=payload.description or "",
        scenario_type=payload.scenario_type,
        execution_mode="SIMULATED",  # Enforce simulation lock
        recovery_enabled=payload.recovery_enabled,
        target_service_id=payload.target_service_id,
        number_of_runs=payload.number_of_runs,
        random_seed=payload.random_seed,
        configuration=payload.configuration or {},
        test_conditions=payload.test_conditions or {},
        status="pending",
        results_summary={},
    )
    db.add(experiment)
    await db.commit()
    stmt = select(Experiment).options(selectinload(Experiment.runs)).where(Experiment.id == exp_id)
    res = await db.execute(stmt)
    created = res.scalar_one()
    return _format_experiment_response(created)


@router.get(
    "",
    response_model=List[ExperimentResponse],
    summary="List all experiments for the organization",
)
async def list_experiments(
    user: RequireViewerDep,
    org: OrgDep,
    db: DatabaseDep,
    scenario_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
) -> List[ExperimentResponse]:
    """Retrieves all benchmark experiments in the current tenant."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.organization_id == org.id)
        .order_by(desc(Experiment.created_at))
    )
    if scenario_type:
        stmt = stmt.where(Experiment.scenario_type == scenario_type)
    if status_filter:
        stmt = stmt.where(Experiment.status == status_filter)

    res = await db.execute(stmt)
    experiments = res.scalars().all()
    return [_format_experiment_response(e, include_runs=False) for e in experiments]


@router.get(
    "/{experiment_id}",
    response_model=ExperimentResponse,
    summary="Get detailed experiment with runs",
)
async def get_experiment(
    experiment_id: str,
    user: RequireViewerDep,
    org: OrgDep,
    db: DatabaseDep,
) -> ExperimentResponse:
    """Retrieves experiment configuration, summary metrics, and all execution runs."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    experiment = res.scalar_one_or_none()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )
    return _format_experiment_response(experiment, include_runs=True)


@router.post(
    "/{experiment_id}/start",
    response_model=ExperimentResponse,
    summary="Start execution of an experiment",
)
async def start_experiment(
    experiment_id: str,
    user: RequireOperatorDep,
    org: OrgDep,
    db: DatabaseDep,
) -> ExperimentResponse:
    """
    Executes all configured runs for the experiment.
    Runs are executed deterministically using pinned seeds.
    """
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    experiment = res.scalar_one_or_none()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )

    if experiment.status in ("running", "completed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment '{experiment_id}' is already {experiment.status}. Create a new experiment to run another trial.",
        )

    # Execute
    updated_exp = await ExperimentRunner.execute_experiment(db, experiment.id)
    return _format_experiment_response(updated_exp, include_runs=True)


@router.post(
    "/{experiment_id}/cancel",
    response_model=ExperimentResponse,
    summary="Cancel an in-progress experiment",
)
async def cancel_experiment(
    experiment_id: str,
    user: RequireOperatorDep,
    org: OrgDep,
    db: DatabaseDep,
) -> ExperimentResponse:
    """Cancels a running or pending experiment gracefully."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    experiment = res.scalar_one_or_none()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )

    if experiment.status not in ("running", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel experiment in status '{experiment.status}'.",
        )

    experiment.status = "cancelled"
    experiment.completed_at = utc_now()
    await db.commit()
    stmt = select(Experiment).options(selectinload(Experiment.runs)).where(Experiment.id == experiment_id)
    res = await db.execute(stmt)
    updated = res.scalar_one()
    return _format_experiment_response(updated, include_runs=True)


@router.get(
    "/{experiment_id}/runs",
    response_model=List[ExperimentRunResponse],
    summary="List all runs for an experiment",
)
async def list_experiment_runs(
    experiment_id: str,
    user: RequireViewerDep,
    org: OrgDep,
    db: DatabaseDep,
) -> List[ExperimentRunResponse]:
    """Retrieves all individual runs and raw telemetry samples for an experiment."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    experiment = res.scalar_one_or_none()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )
    return [_format_run_response(r) for r in experiment.runs]


@router.get(
    "/{experiment_id}/analytics",
    response_model=ExperimentAnalyticsResponse,
    summary="Compute aggregate metrics and statistical distributions",
)
async def get_experiment_analytics(
    experiment_id: str,
    user: RequireViewerDep,
    org: OrgDep,
    db: DatabaseDep,
) -> ExperimentAnalyticsResponse:
    """Computes distribution statistics (mean, median, std_dev, p95) and safety rates."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    experiment = res.scalar_one_or_none()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )
    return build_experiment_analytics(experiment)


@router.get(
    "/{experiment_id}/compare",
    response_model=ExperimentComparisonResponse,
    summary="Compare recovery enabled vs disabled experiments",
)
async def compare_experiment_modes(
    experiment_id: str,
    user: RequireViewerDep,
    org: OrgDep,
    db: DatabaseDep,
    control_experiment_id: Optional[str] = None,
) -> ExperimentComparisonResponse:
    """
    Performs pairwise comparison between Recovery Enabled and Recovery Disabled experiments.
    Matches identical scenario and seed to compute empirical MTTR and outage reductions.
    """
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    exp_a = res.scalar_one_or_none()
    if not exp_a:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )

    exp_b = None
    if control_experiment_id:
        stmt_b = (
            select(Experiment)
            .options(selectinload(Experiment.runs))
            .where(Experiment.id == control_experiment_id, Experiment.organization_id == org.id)
        )
        res_b = await db.execute(stmt_b)
        exp_b = res_b.scalar_one_or_none()
    else:
        # Auto-match matching counterpart in org
        target_rec_enabled = not exp_a.recovery_enabled
        stmt_b = (
            select(Experiment)
            .options(selectinload(Experiment.runs))
            .where(
                Experiment.organization_id == org.id,
                Experiment.scenario_type == exp_a.scenario_type,
                Experiment.random_seed == exp_a.random_seed,
                Experiment.recovery_enabled == target_rec_enabled,
                Experiment.status == "completed",
            )
            .order_by(desc(Experiment.created_at))
        )
        res_b = await db.execute(stmt_b)
        exp_b = res_b.scalar_one_or_none()

    enabled_exp = exp_a if exp_a.recovery_enabled else exp_b
    disabled_exp = exp_b if exp_a.recovery_enabled else exp_a

    return compare_experiments(
        enabled_exp=enabled_exp,
        disabled_exp=disabled_exp,
        scenario_type=exp_a.scenario_type,
        random_seed=exp_a.random_seed,
    )


@router.get(
    "/{experiment_id}/report",
    summary="Download experiment research report (PDF or JSON)",
)
async def download_experiment_report(
    experiment_id: str,
    user: RequireViewerDep,
    org: OrgDep,
    db: DatabaseDep,
    report_format: Literal["pdf", "json"] = Query("pdf", alias="format"),
):
    """Generates and downloads publication-grade research reports in PDF or JSON format."""
    stmt = (
        select(Experiment)
        .options(selectinload(Experiment.runs))
        .where(Experiment.id == experiment_id, Experiment.organization_id == org.id)
    )
    res = await db.execute(stmt)
    experiment = res.scalar_one_or_none()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found.",
        )

    if report_format == "json":
        report_data = generate_experiment_json_report(experiment)
        return report_data
    else:
        pdf_bytes = generate_experiment_pdf_report(experiment)
        filename = f"autoheal_experiment_report_{experiment.id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/pdf",
            },
        )
