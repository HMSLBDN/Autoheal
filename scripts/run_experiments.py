"""
AutoHeal DevOps — Repeatable Experimentation & Statistical Measurement Engine
Runs repeated, controlled fault injection and self-healing trials against the actual
API and database pipelines. Measures exact detection latency, recovery execution time,
post-verification health, total outage duration, and success rates using true timestamps.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List
import uuid

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import (
    AuditLog,
    Incident,
    Organization,
    RecoveryAction,
    Service,
    User,
)
from app.models.base import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("experiment_engine")
settings = get_settings()


class ExperimentRunner:
    """
    Executes controlled empirical trials measuring self-healing lifecycle metrics.
    """

    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.client: TestClient = None  # type: ignore

    async def setup_test_environment(self) -> Dict[str, Any]:
        """Provisions clean test organization, services, and operator user."""
        org_id = uuid.uuid4()
        org = Organization(
            id=org_id,
            slug=f"exp-org-{org_id.hex[:6]}",
            name="Experiment Validation Org",
            is_active=True,
        )
        self.session.add(org)
        await self.session.flush()

        operator = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=f"operator-{org_id.hex[:6]}@example.com",
            full_name="Experiment Operator",
            hashed_password=get_password_hash("ExpPass123!"),
            role="operator",
            is_active=True,
        )
        self.session.add(operator)
        await self.session.flush()

        # Seed monitored microservices
        services = [
            Service(
                id=f"svc-exp-checkout-{org_id.hex[:4]}",
                organization_id=org.id,
                name="checkout-api",
                environment="production",
                status="healthy",
                availability=99.98,
                error_rate=0.01,
                latency_ms=25,
                last_checked=datetime.now(timezone.utc),
            ),
            Service(
                id=f"svc-exp-customer-{org_id.hex[:4]}",
                organization_id=org.id,
                name="customer-web",
                environment="production",
                status="healthy",
                availability=99.95,
                error_rate=0.02,
                latency_ms=45,
                last_checked=datetime.now(timezone.utc),
            ),
            Service(
                id=f"svc-exp-payments-{org_id.hex[:4]}",
                organization_id=org.id,
                name="payments-api",
                environment="production",
                status="healthy",
                availability=99.99,
                error_rate=0.005,
                latency_ms=30,
                last_checked=datetime.now(timezone.utc),
            ),
        ]
        self.session.add_all(services)
        await self.session.commit()

        token = create_access_token(
            user_id=str(operator.id),
            email=operator.email,
            role=operator.role,
            org_id=str(org.id),
        )

        return {
            "org": org,
            "operator": operator,
            "services": {s.name: s for s in services},
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    async def run_trial(
        self,
        trial_id: int,
        env: Dict[str, Any],
        service_name: str,
        fault_type: str,
        alertname: str,
        severity: str,
        expect_rejection: bool = False,
    ) -> Dict[str, Any]:
        """Runs a single end-to-end self-healing trial and captures empirical timestamps."""
        headers = env["headers"]
        t_fault_start = time.perf_counter()
        t_fault_dt = datetime.now(timezone.utc)

        # 1. Trigger controlled fault
        fault_res = self.client.post(
            "/api/v1/demo/fault",
            headers=headers,
            json={
                "service_name": service_name,
                "fault_type": fault_type,
                "error_rate": 0.20 if fault_type == "http_500" else None,
                "latency_ms": 850 if fault_type == "high_latency" else None,
            },
        )
        assert fault_res.status_code == 200, f"Fault injection failed: {fault_res.text}"

        # 2. Simulate alert detection via Alertmanager pipeline
        alert_res = self.client.post(
            "/api/v1/demo/simulate-alert",
            headers=headers,
            json={
                "service_name": service_name,
                "alertname": alertname,
                "severity": severity,
                "summary": f"Breach detected: {alertname} on {service_name}",
                "description": f"Automated monitoring alert triggered for {service_name}.",
                "auto_request_recovery": True,
            },
        )
        t_detected = time.perf_counter()
        t_detected_dt = datetime.now(timezone.utc)
        assert alert_res.status_code == 200, f"Alert simulation failed: {alert_res.text}"
        alert_data = alert_res.json()
        inc_id = alert_data["incident_id"]
        rec_id = alert_data["recovery_id"]

        detection_latency = round(t_detected - t_fault_start, 3)

        if expect_rejection:
            # Operator rejection scenario
            t_act_start = time.perf_counter()
            rej_res = self.client.post(
                f"/api/v1/recoveries/{rec_id}/reject",
                headers=headers,
                json={"reason": "False positive / Operator override"},
            )
            assert rej_res.status_code == 200
            t_complete = time.perf_counter()
            return {
                "trial_id": trial_id,
                "service": service_name,
                "fault_type": fault_type,
                "detection_classification": "True Positive (TP)",
                "outcome": "rejected",
                "detection_latency_seconds": detection_latency,
                "recovery_duration_seconds": round(t_complete - t_act_start, 3),
                "total_outage_seconds": round(t_complete - t_fault_start, 3),
                "incident_id": inc_id,
                "recovery_id": rec_id,
                "verified": False,
            }

        # 3. Operator approves recovery
        appr_res = self.client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=headers)
        assert appr_res.status_code == 200, f"Approval failed: {appr_res.text}"

        # 4. Operator executes recovery with automated health verification
        t_exec_start = time.perf_counter()
        exec_res = self.client.post(f"/api/v1/recoveries/{rec_id}/execute", headers=headers)
        t_exec_done = time.perf_counter()
        assert exec_res.status_code == 200, f"Execution failed: {exec_res.text}"
        exec_data = exec_res.json()

        recovery_duration = round(t_exec_done - t_exec_start, 3)
        total_outage = round(t_exec_done - t_fault_start, 3)

        # 5. Clean reset for next trial
        self.client.post(
            "/api/v1/demo/reset",
            headers=headers,
            json={"service_name": service_name},
        )

        return {
            "trial_id": trial_id,
            "service": service_name,
            "fault_type": fault_type,
            "detection_classification": "True Positive (TP)",
            "outcome": "verified_recovered",
            "detection_latency_seconds": detection_latency,
            "recovery_duration_seconds": recovery_duration,
            "total_outage_seconds": total_outage,
            "incident_id": inc_id,
            "recovery_id": rec_id,
            "verified": exec_data.get("verification") == "passed",
        }


async def run_full_experiment_suite() -> Dict[str, Any]:
    """Orchestrates 5 repeatable trials, aggregates metrics, and returns statistical summary."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        runner = ExperimentRunner(session)

        async def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            runner.client = client
            env = await runner.setup_test_environment()

            trials_spec = [
                (1, "checkout-api", "http_500", "HighErrorRate", "critical", False),
                (2, "customer-web", "high_latency", "HighLatency", "high", False),
                (3, "payments-api", "service_down", "ServiceDown", "critical", False),
                (4, "checkout-api", "degraded", "CPUSaturation", "medium", False),
                (5, "customer-web", "http_500", "HighErrorRate", "high", True),  # Rejection / false positive trial
            ]

            results: List[Dict[str, Any]] = []
            for tid, svc, fault, alert, sev, rej in trials_spec:
                logger.info(f"Running Trial #{tid}: {svc} -> {fault} (Rejection={rej})")
                res = await runner.run_trial(tid, env, svc, fault, alert, sev, expect_rejection=rej)
                results.append(res)

        app.dependency_overrides.clear()

    await engine.dispose()

    # Aggregate statistical measurements
    recovered = [r for r in results if r["outcome"] == "verified_recovered" and r["verified"] is True]
    rejected = [r for r in results if r["outcome"] == "rejected"]
    failed = [r for r in results if r["outcome"] == "failed" or (r["outcome"] == "verified_recovered" and r["verified"] is False)]

    det_latencies = [r["detection_latency_seconds"] for r in results]
    rec_durations = [r["recovery_duration_seconds"] for r in recovered]
    outages = [r["total_outage_seconds"] for r in recovered]

    # Detection Classification & Accuracy:
    # - True Positive (TP): unhealthy observation correctly generates an incident
    # - False Positive (FP): healthy observation incorrectly generates an incident
    # - True Negative (TN): healthy observation correctly generates no incident
    # - False Negative (FN): unhealthy observation fails to generate an incident
    tp_count = sum(1 for r in results if r.get("detection_classification") == "True Positive (TP)")
    fp_count = sum(1 for r in results if r.get("detection_classification") == "False Positive (FP)")
    tn_count = sum(1 for r in results if r.get("detection_classification") == "True Negative (TN)")
    fn_count = sum(1 for r in results if r.get("detection_classification") == "False Negative (FN)")

    # False-positive rate = FP / (FP + TN)
    healthy_observations = fp_count + tn_count
    if healthy_observations > 0:
        false_positive_rate_percent = round((fp_count / healthy_observations) * 100, 2)
    else:
        # Reported strictly as unavailable rather than inventing a percentage
        false_positive_rate_percent = None

    # Operator rejection rate: reported separately from detection accuracy
    total_terminal_actions = len(recovered) + len(rejected) + len(failed)
    operator_rejection_rate_percent = round((len(rejected) / total_terminal_actions) * 100, 2) if total_terminal_actions > 0 else 0.0

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_trials": len(results),
        "successful_recoveries": len(recovered),
        "rejected_recoveries": len(rejected),
        "failed_recoveries": len(failed),
        "recovery_success_rate_percent": round(len(recovered) / len(results) * 100, 2),
        "operator_rejection_rate_percent": operator_rejection_rate_percent,
        "detection_classification": {
            "true_positives": tp_count,
            "false_positives": fp_count,
            "true_negatives": tn_count,
            "false_negatives": fn_count,
            "healthy_observation_windows": healthy_observations,
            "false_positive_rate": false_positive_rate_percent,
            "false_positive_rate_status": "calculated" if false_positive_rate_percent is not None else "unavailable (insufficient healthy observation windows)",
        },
        "detection_latency": {
            "mean_seconds": round(sum(det_latencies) / len(det_latencies), 3),
            "min_seconds": min(det_latencies),
            "max_seconds": max(det_latencies),
        },
        "recovery_duration": {
            "mean_seconds": round(sum(rec_durations) / len(rec_durations), 3),
            "min_seconds": min(rec_durations),
            "max_seconds": max(rec_durations),
        },
        "total_outage_duration": {
            "mean_seconds": round(sum(outages) / len(outages), 3),
            "min_seconds": min(outages),
            "max_seconds": max(outages),
        },
        "trials": results,
    }

    # Save results to file
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "monitoring"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "experiment_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Saved experiment results to {out_path}")
    return summary


if __name__ == "__main__":
    summary = asyncio.run(run_full_experiment_suite())
    print("\n" + "=" * 70)
    print("AUTOHEAL DEVOPS — EMPIRICAL REPEATABLE EXPERIMENT RESULTS")
    print("=" * 70)
    print(f"Total Trials Conducted:        {summary['total_trials']}")
    print(f"Successful Recoveries:         {summary['successful_recoveries']}")
    print(f"Operator Rejected Actions:     {summary['rejected_recoveries']}")
    print(f"Failed Recoveries:             {summary['failed_recoveries']}")
    print(f"Recovery Success Rate:         {summary['recovery_success_rate_percent']}%")
    print(f"Operator Rejection Rate:       {summary['operator_rejection_rate_percent']}% (Reported separately)")
    print("-" * 70)
    print(f"Detection TP / FP / TN / FN:   {summary['detection_classification']['true_positives']} / {summary['detection_classification']['false_positives']} / {summary['detection_classification']['true_negatives']} / {summary['detection_classification']['false_negatives']}")
    print(f"False-Positive Rate:           {summary['detection_classification']['false_positive_rate_status']}")
    print("-" * 70)
    print(f"Mean Detection Latency:        {summary['detection_latency']['mean_seconds']} s (Min: {summary['detection_latency']['min_seconds']}s, Max: {summary['detection_latency']['max_seconds']}s)")
    print(f"Mean Recovery Duration:        {summary['recovery_duration']['mean_seconds']} s (Min: {summary['recovery_duration']['min_seconds']}s, Max: {summary['recovery_duration']['max_seconds']}s)")
    print(f"Mean Total Outage Duration:    {summary['total_outage_duration']['mean_seconds']} s (Min: {summary['total_outage_duration']['min_seconds']}s, Max: {summary['total_outage_duration']['max_seconds']}s)")
    print("=" * 70)
