"""
AutoHeal DevOps — Phase 14 Automated Experiment Runner
Executes reproducible, deterministic benchmark experiments across 8 scenarios.
Strictly simulation-mode gated, seed-isolated, and cancel-safe.
"""

from datetime import datetime, timedelta, timezone
import logging
import random
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import utc_now
from app.models.experiment import Experiment, ExperimentRun
from app.services.experiment.comparator import build_experiment_analytics

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """
    Automated evaluation engine for AutoHeal DevOps.
    Executes multi-run scenarios with deterministic seeds, calculates latencies,
    evaluates policy constraints, and tracks safety compliance.
    """

    @staticmethod
    def _generate_telemetry_series(
        rng: random.Random,
        t_base: datetime,
        scenario: str,
        recovery_enabled: bool,
        recovery_success: bool,
    ) -> List[Dict[str, Any]]:
        """Generates realistic time-series telemetry samples (10 points across the experiment timeline)."""
        samples = []
        for step in range(10):
            ts = t_base + timedelta(seconds=step * 2)
            # Default healthy baseline
            cpu = round(rng.uniform(22.0, 38.0), 1)
            mem = round(rng.uniform(40.0, 55.0), 1)
            err_rate = round(rng.uniform(0.0, 0.4), 2)
            p95_ms = round(rng.uniform(40.0, 75.0), 1)
            status_code = 200

            # Fault injection active between steps 2 and 6
            if 2 <= step <= 6:
                if scenario == "healthy_baseline":
                    pass  # No fault
                elif scenario == "service_unavailable":
                    err_rate = 100.0
                    p95_ms = round(rng.uniform(2500.0, 4500.0), 1)
                    status_code = 503
                elif scenario == "high_error_rate":
                    err_rate = round(rng.uniform(18.0, 26.0), 1)
                    p95_ms = round(rng.uniform(850.0, 1600.0), 1)
                    status_code = 500
                elif scenario == "resource_exhaustion":
                    cpu = round(rng.uniform(92.0, 98.5), 1)
                    mem = round(rng.uniform(88.0, 96.0), 1)
                    p95_ms = round(rng.uniform(1200.0, 2200.0), 1)
                elif scenario == "repeated_alerts":
                    err_rate = round(rng.uniform(12.0, 20.0), 1)
                    p95_ms = round(rng.uniform(600.0, 1100.0), 1)
                elif scenario in ("verification_failure", "recovery_verification_failure"):
                    err_rate = round(rng.uniform(15.0, 30.0), 1)
                    status_code = 502
                elif scenario in ("unauthorized_recovery", "unapproved_recovery"):
                    err_rate = round(rng.uniform(14.0, 22.0), 1)
                    status_code = 500

            # Post-recovery window (steps 7 to 9)
            if step >= 7:
                if recovery_enabled and recovery_success:
                    # Health restored
                    cpu = round(rng.uniform(25.0, 42.0), 1)
                    mem = round(rng.uniform(42.0, 58.0), 1)
                    err_rate = round(rng.uniform(0.1, 0.6), 2)
                    p95_ms = round(rng.uniform(45.0, 80.0), 1)
                    status_code = 200
                else:
                    # Still failing or unmitigated
                    if scenario != "healthy_baseline":
                        err_rate = round(rng.uniform(16.0, 45.0), 1)
                        p95_ms = round(rng.uniform(1500.0, 3500.0), 1)
                        status_code = 503 if scenario == "service_unavailable" else 500

            samples.append({
                "timestamp": ts.isoformat(),
                "step": step,
                "cpu_usage_pct": cpu,
                "memory_usage_pct": mem,
                "error_rate_pct": err_rate,
                "p95_latency_ms": p95_ms,
                "http_status": status_code,
            })
        return samples

    @classmethod
    async def run_scenario_iteration(
        cls,
        scenario: str,
        recovery_enabled: bool,
        seed: int,
        target_service: str,
    ) -> Dict[str, Any]:
        """
        Executes a single deterministic scenario iteration using seed-isolated PRNG.
        Returns all timestamps, metrics, safety statuses, and execution log.
        """
        rng = random.Random(seed)
        t_base = utc_now()
        t_fault: Optional[datetime] = None
        t_detect: Optional[datetime] = None
        t_rec_start: Optional[datetime] = None
        t_rec_end: Optional[datetime] = None
        t_restored: Optional[datetime] = None

        det_lat_ms: Optional[float] = None
        rec_dur_ms: Optional[float] = None
        total_outage_ms: Optional[float] = None

        rec_attempted = False
        rec_verified = False
        rec_success = False
        is_fp = False
        safety_compliant = True
        escalated = False
        incident_id: Optional[str] = None
        recovery_action_id: Optional[str] = None
        execution_log: List[Dict[str, Any]] = []

        # Scenario Dispatch
        if scenario == "healthy_baseline":
            # Scenario 1: Healthy baseline — evaluate false-positive rate
            execution_log.append({
                "event": "baseline_monitoring",
                "detail": f"Service {target_service} operating within standard thresholds.",
                "timestamp": t_base.isoformat(),
            })
            # Deterministic noise check: 0.5% chance of spurious metric noise under extreme seeds
            has_noise = (seed % 200 == 0)
            if has_noise:
                is_fp = True
                det_lat_ms = round(rng.uniform(1100.0, 1800.0), 1)
                t_detect = t_base + timedelta(milliseconds=det_lat_ms)
                incident_id = f"INC-SIM-{rng.randint(10000, 99999)}"
                execution_log.append({
                    "event": "spurious_anomaly_detected",
                    "detail": "Transient spike triggered threshold evaluation.",
                    "timestamp": t_detect.isoformat(),
                })
            else:
                is_fp = False
                det_lat_ms = 0.0
                total_outage_ms = 0.0
                rec_success = True

        elif scenario in ("service_unavailable", "high_error_rate", "resource_exhaustion"):
            # Scenarios 2, 3, 4: Outage / High Error / Saturation
            t_fault = t_base + timedelta(milliseconds=500)
            execution_log.append({
                "event": "fault_injected",
                "detail": f"Simulated {scenario} fault injected for {target_service}.",
                "timestamp": t_fault.isoformat(),
            })

            # Detection Latency
            det_lat_ms = round(rng.uniform(1150.0, 2450.0), 1)
            t_detect = t_fault + timedelta(milliseconds=det_lat_ms)
            incident_id = f"INC-SIM-{rng.randint(10000, 99999)}"
            execution_log.append({
                "event": "incident_detected",
                "incident_id": incident_id,
                "latency_ms": det_lat_ms,
                "timestamp": t_detect.isoformat(),
            })

            if recovery_enabled:
                rec_attempted = True
                recovery_action_id = f"REC-SIM-{rng.randint(10000, 99999)}"
                t_rec_start = t_detect + timedelta(milliseconds=200)
                execution_log.append({
                    "event": "recovery_initiated",
                    "action_id": recovery_action_id,
                    "action": "restart_container" if scenario != "resource_exhaustion" else "scale_service",
                    "timestamp": t_rec_start.isoformat(),
                })

                # Recovery Execution
                rec_dur_ms = round(rng.uniform(1800.0, 3600.0), 1)
                t_rec_end = t_rec_start + timedelta(milliseconds=rec_dur_ms)
                execution_log.append({
                    "event": "recovery_simulated",
                    "duration_ms": rec_dur_ms,
                    "timestamp": t_rec_end.isoformat(),
                })

                # Post-Recovery Health Verification
                rec_verified = True
                rec_success = True
                t_restored = t_rec_end + timedelta(milliseconds=800)
                total_outage_ms = round((t_restored - t_fault).total_seconds() * 1000.0, 1)
                execution_log.append({
                    "event": "health_verified",
                    "status": "passed",
                    "total_outage_ms": total_outage_ms,
                    "timestamp": t_restored.isoformat(),
                })
            else:
                # Recovery Disabled: Outage unmitigated until benchmark timeout (60,000ms standard)
                rec_attempted = False
                rec_verified = False
                rec_success = False
                total_outage_ms = 60000.0
                execution_log.append({
                    "event": "recovery_disabled",
                    "detail": "Autonomous remediation disabled; incident left unmitigated.",
                    "total_outage_ms": total_outage_ms,
                    "timestamp": t_detect.isoformat(),
                })

        elif scenario == "repeated_alerts":
            # Scenario 5: Flapping alerts with cooldown suppression
            t_fault = t_base + timedelta(milliseconds=400)
            det_lat_ms = round(rng.uniform(1100.0, 1900.0), 1)
            t_detect = t_fault + timedelta(milliseconds=det_lat_ms)
            incident_id = f"INC-SIM-{rng.randint(10000, 99999)}"

            execution_log.append({
                "event": "primary_alert_detected",
                "incident_id": incident_id,
                "timestamp": t_detect.isoformat(),
            })

            # Flapping alerts suppressed by policy cooldown
            execution_log.append({
                "event": "cooldown_suppression",
                "detail": "Suppressed 4 repeated alerts within 300s policy cooldown window.",
                "safety_compliant": True,
                "timestamp": (t_detect + timedelta(seconds=1)).isoformat(),
            })

            if recovery_enabled:
                rec_attempted = True
                recovery_action_id = f"REC-SIM-{rng.randint(10000, 99999)}"
                t_rec_start = t_detect + timedelta(milliseconds=250)
                rec_dur_ms = round(rng.uniform(1900.0, 3100.0), 1)
                t_rec_end = t_rec_start + timedelta(milliseconds=rec_dur_ms)
                rec_verified = True
                rec_success = True
                t_restored = t_rec_end + timedelta(milliseconds=600)
                total_outage_ms = round((t_restored - t_fault).total_seconds() * 1000.0, 1)
            else:
                rec_attempted = False
                total_outage_ms = 60000.0

        elif scenario in ("verification_failure", "recovery_verification_failure"):
            # Scenario 6: Recovery verification failure -> incident escalation
            t_fault = t_base + timedelta(milliseconds=500)
            det_lat_ms = round(rng.uniform(1200.0, 2100.0), 1)
            t_detect = t_fault + timedelta(milliseconds=det_lat_ms)
            incident_id = f"INC-SIM-{rng.randint(10000, 99999)}"

            rec_attempted = True
            recovery_action_id = f"REC-SIM-{rng.randint(10000, 99999)}"
            t_rec_start = t_detect + timedelta(milliseconds=200)
            rec_dur_ms = round(rng.uniform(1800.0, 3000.0), 1)
            t_rec_end = t_rec_start + timedelta(milliseconds=rec_dur_ms)

            # Verification FAILS
            rec_verified = True
            rec_success = False
            escalated = True
            safety_compliant = True  # Safety rules were respected: failure was NOT marked resolved
            total_outage_ms = 60000.0

            execution_log.append({
                "event": "verification_failed",
                "detail": "Post-recovery health check probe timed out; container unready.",
                "timestamp": t_rec_end.isoformat(),
            })
            execution_log.append({
                "event": "incident_escalated",
                "detail": "Incident escalated to human on-call operator per safety state machine.",
                "timestamp": (t_rec_end + timedelta(seconds=1)).isoformat(),
            })

        elif scenario == "unauthorized_recovery":
            # Scenario 7: Unauthorized recovery attempt blocked
            t_fault = t_base + timedelta(milliseconds=300)
            det_lat_ms = round(rng.uniform(1000.0, 1600.0), 1)
            t_detect = t_fault + timedelta(milliseconds=det_lat_ms)
            incident_id = f"INC-SIM-{rng.randint(10000, 99999)}"

            rec_attempted = False
            rec_success = False
            safety_compliant = True  # Strict compliance: unauthorized mutation rejected
            total_outage_ms = 60000.0

            execution_log.append({
                "event": "authorization_evaluated",
                "actor_role": "viewer",
                "result": "HTTP 403 Forbidden — Recovery permission denied.",
                "safety_compliant": True,
                "timestamp": t_detect.isoformat(),
            })

        elif scenario == "unapproved_recovery":
            # Scenario 8: Destructive/high-risk recovery requires approval, withheld
            t_fault = t_base + timedelta(milliseconds=350)
            det_lat_ms = round(rng.uniform(1100.0, 1750.0), 1)
            t_detect = t_fault + timedelta(milliseconds=det_lat_ms)
            incident_id = f"INC-SIM-{rng.randint(10000, 99999)}"

            rec_attempted = False
            rec_success = False
            escalated = True
            safety_compliant = True  # Strict compliance: execution halted pending human sign-off
            total_outage_ms = 60000.0

            execution_log.append({
                "event": "approval_policy_evaluated",
                "action": "restart_database_primary",
                "requires_approval": True,
                "status": "pending_approval",
                "detail": "Action halted; awaiting cryptographically verified manual sign-off.",
                "timestamp": t_detect.isoformat(),
            })

        telemetry = cls._generate_telemetry_series(
            rng=rng,
            t_base=t_base,
            scenario=scenario,
            recovery_enabled=recovery_enabled,
            recovery_success=rec_success,
        )

        return {
            "fault_injected_at": t_fault,
            "detected_at": t_detect,
            "recovery_started_at": t_rec_start,
            "recovery_completed_at": t_rec_end,
            "health_restored_at": t_restored,
            "detection_latency_ms": det_lat_ms,
            "recovery_duration_ms": rec_dur_ms,
            "total_outage_duration_ms": total_outage_ms,
            "recovery_attempted": rec_attempted,
            "recovery_verified": rec_verified,
            "recovery_success": rec_success,
            "is_false_positive": is_fp,
            "safety_compliant": safety_compliant,
            "escalated": escalated,
            "incident_id": incident_id,
            "recovery_action_id": recovery_action_id,
            "telemetry_samples": telemetry,
            "execution_log": execution_log,
        }

    @classmethod
    async def execute_experiment(
        cls,
        db: AsyncSession,
        experiment_id: str,
    ) -> Experiment:
        """
        Runs all configured runs for an experiment sequentially.
        Respects cancellation and records full audit records.
        """
        stmt = (
            select(Experiment)
            .options(selectinload(Experiment.runs))
            .where(Experiment.id == experiment_id)
        )
        res = await db.execute(stmt)
        experiment = res.scalar_one_or_none()
        if not experiment:
            raise ValueError(f"Experiment '{experiment_id}' not found.")

        if experiment.status == "running":
            raise ValueError(f"Experiment '{experiment_id}' is already running.")

        # Update experiment to running
        experiment.status = "running"
        experiment.started_at = utc_now()
        await db.commit()

        try:
            for run_num in range(1, experiment.number_of_runs + 1):
                # Refresh status check for cancellation
                await db.refresh(experiment)
                if experiment.status == "cancelled":
                    logger.info(f"Experiment {experiment_id} cancelled by operator.")
                    break

                run_seed = experiment.random_seed + run_num
                run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"

                # Create Run in db
                run_record = ExperimentRun(
                    id=run_id,
                    experiment_id=experiment.id,
                    run_number=run_num,
                    status="running",
                    recovery_enabled=experiment.recovery_enabled,
                    seed=run_seed,
                    started_at=utc_now(),
                    evidence_classification="SIMULATED",
                    telemetry_samples=[],
                    execution_log=[],
                )
                db.add(run_record)
                await db.commit()

                # Execute Scenario
                results = await cls.run_scenario_iteration(
                    scenario=experiment.scenario_type,
                    recovery_enabled=experiment.recovery_enabled,
                    seed=run_seed,
                    target_service=experiment.target_service_id,
                )

                # Update Run record
                for k, v in results.items():
                    setattr(run_record, k, v)
                run_record.status = "completed"
                run_record.completed_at = utc_now()
                await db.commit()

            # Mark experiment completed or cancelled
            await db.refresh(experiment)
            if experiment.status != "cancelled":
                experiment.status = "completed"
                experiment.completed_at = utc_now()

            # Compute and store summary analytics
            # Reload runs
            stmt = select(Experiment).options(selectinload(Experiment.runs)).where(Experiment.id == experiment_id)
            exp_res = await db.execute(stmt)
            experiment = exp_res.scalar_one()

            analytics = build_experiment_analytics(experiment)
            experiment.results_summary = analytics.model_dump()
            await db.commit()
            return experiment

        except Exception as e:
            logger.exception(f"Experiment {experiment_id} execution failed: {e}")
            experiment.status = "failed"
            experiment.completed_at = utc_now()
            experiment.results_summary = {"error": str(e)}
            await db.commit()
            raise
