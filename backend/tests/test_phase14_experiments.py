"""
AutoHeal DevOps — Phase 14 Empirical Benchmark & Evaluation Pytest Suite
Verifies:
1. Experiment lifecycle management & strict tenant isolation.
2. Hard-locked simulation mode (RECOVERY_SIMULATION_MODE=true).
3. 8 Deterministic benchmark scenarios (healthy, 503 outage, high error, saturation, flapping, verification failure, unauthorized, unapproved).
4. Dual comparison modes (Recovery Enabled vs Recovery Disabled).
5. Rigorous metric calculations, distributions, and sample-size awareness.
6. Empirical MTTR reduction & comparative analytics.
7. Graceful cancellation without orphan state.
8. Publication-ready research reports (PDF and JSON export).
"""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.experiment import Experiment, ExperimentRun
from app.models.organization import Organization
from app.models.user import User
from app.services.experiment import (
    ExperimentRunner,
    calculate_distribution,
    compare_experiments,
    generate_experiment_json_report,
    generate_experiment_pdf_report,
)


async def get_phase14_test_data(db_session):
    """Provisions isolated tenant, admin, operator, viewer, and Org B for Phase 14 tests."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        slug=f"exp-org-{uuid.uuid4().hex[:6]}",
        name="Phase 14 Benchmark Org",
        plan="enterprise",
        is_active=True,
    )
    db_session.add(org)

    # Admin user
    admin_id = uuid.uuid4()
    admin_user = User(
        id=admin_id,
        organization_id=org_id,
        email=f"admin-{uuid.uuid4().hex[:6]}@benchmark.local",
        full_name="Benchmark Admin",
        hashed_password="[TEST_HASH]",
        role="admin",
        is_active=True,
    )
    db_session.add(admin_user)

    # Operator user
    operator_id = uuid.uuid4()
    operator_user = User(
        id=operator_id,
        organization_id=org_id,
        email=f"operator-{uuid.uuid4().hex[:6]}@benchmark.local",
        full_name="Benchmark Operator",
        hashed_password="[TEST_HASH]",
        role="operator",
        is_active=True,
    )
    db_session.add(operator_user)

    # Viewer user
    viewer_id = uuid.uuid4()
    viewer_user = User(
        id=viewer_id,
        organization_id=org_id,
        email=f"viewer-{uuid.uuid4().hex[:6]}@benchmark.local",
        full_name="Benchmark Viewer",
        hashed_password="[TEST_HASH]",
        role="viewer",
        is_active=True,
    )
    db_session.add(viewer_user)

    # Separate Org B for tenant isolation tests
    org_b_id = uuid.uuid4()
    org_b = Organization(
        id=org_b_id,
        slug=f"org-b-{uuid.uuid4().hex[:6]}",
        name="Tenant B Isolation Org",
        plan="pro",
        is_active=True,
    )
    db_session.add(org_b)

    org_b_admin_id = uuid.uuid4()
    org_b_admin = User(
        id=org_b_admin_id,
        organization_id=org_b_id,
        email=f"admin-b-{uuid.uuid4().hex[:6]}@tenantb.local",
        full_name="Tenant B Admin",
        hashed_password="[TEST_HASH]",
        role="admin",
        is_active=True,
    )
    db_session.add(org_b_admin)

    await db_session.commit()

    # Generate tokens
    admin_token = create_access_token(str(admin_id), admin_user.email, "admin", str(org_id))
    operator_token = create_access_token(str(operator_id), operator_user.email, "operator", str(org_id))
    viewer_token = create_access_token(str(viewer_id), viewer_user.email, "viewer", str(org_id))
    org_b_token = create_access_token(str(org_b_admin_id), org_b_admin.email, "admin", str(org_b_id))

    return {
        "org_id": org_id,
        "admin_user": admin_user,
        "operator_user": operator_user,
        "viewer_user": viewer_user,
        "admin_token": admin_token,
        "operator_token": operator_token,
        "viewer_token": viewer_token,
        "org_b_id": org_b_id,
        "org_b_token": org_b_token,
    }


@pytest.mark.asyncio
async def test_01_create_experiment_operator_success(db_session):
    """Verifies that an Operator can create a new experiment with default simulation mode."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "name": "Checkout API 503 Resiliency Benchmark",
            "description": "Evaluate MTTR and policy evaluation under HTTP 503 outage.",
            "scenario_type": "service_unavailable",
            "recovery_enabled": True,
            "target_service_id": "checkout-api",
            "number_of_runs": 5,
            "random_seed": 42,
        }
        res = await ac.post(
            "/api/v1/experiments",
            json=payload,
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["name"] == payload["name"]
        assert body["scenario_type"] == "service_unavailable"
        assert body["execution_mode"] == "SIMULATED"
        assert body["recovery_enabled"] is True
        assert body["number_of_runs"] == 5
        assert body["status"] == "pending"
        assert body["id"].startswith("EXP-")


@pytest.mark.asyncio
async def test_02_create_experiment_viewer_forbidden(db_session):
    """Verifies that a Viewer role cannot create an experiment (403 Forbidden)."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/experiments",
            json={
                "name": "Unauthorized Test",
                "scenario_type": "healthy_baseline",
            },
            headers={"Authorization": f"Bearer {data['viewer_token']}"},
        )
        assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_03_create_experiment_validation_bounds(db_session):
    """Verifies bounds checking for number_of_runs (1-20) and non-negative seed."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Invalid number_of_runs (> 20)
        res_large = await ac.post(
            "/api/v1/experiments",
            json={"name": "Too Many Runs", "scenario_type": "healthy_baseline", "number_of_runs": 25},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res_large.status_code == 422

        # Invalid seed (< 0)
        res_neg = await ac.post(
            "/api/v1/experiments",
            json={"name": "Negative Seed", "scenario_type": "healthy_baseline", "random_seed": -5},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert res_neg.status_code == 422


@pytest.mark.asyncio
async def test_04_simulation_mode_hard_lock(db_session):
    """Verifies that execution_mode is strictly SIMULATED regardless of input payload."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/experiments",
            json={
                "name": "Production Override Attempt",
                "scenario_type": "service_unavailable",
                "execution_mode": "PRODUCTION_LIVE",  # Should be ignored/overridden to SIMULATED
            },
            headers={"Authorization": f"Bearer {data['admin_token']}"},
        )
        assert res.status_code == 201
        assert res.json()["execution_mode"] == "SIMULATED"


@pytest.mark.asyncio
async def test_05_list_and_filter_experiments(db_session):
    """Verifies experiment listing and filtering by scenario_type."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create 2 experiments
        await ac.post(
            "/api/v1/experiments",
            json={"name": "Exp 1", "scenario_type": "healthy_baseline"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        await ac.post(
            "/api/v1/experiments",
            json={"name": "Exp 2", "scenario_type": "service_unavailable"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )

        # List all
        list_all = await ac.get("/api/v1/experiments", headers={"Authorization": f"Bearer {data['viewer_token']}"})
        assert list_all.status_code == 200
        assert len(list_all.json()) >= 2

        # Filter by scenario
        list_filtered = await ac.get(
            "/api/v1/experiments?scenario_type=healthy_baseline",
            headers={"Authorization": f"Bearer {data['viewer_token']}"},
        )
        assert list_filtered.status_code == 200
        for exp in list_filtered.json():
            assert exp["scenario_type"] == "healthy_baseline"


@pytest.mark.asyncio
async def test_06_scenario_1_healthy_baseline_execution(db_session):
    """Verifies Scenario 1 (healthy baseline): 0 false positives, 0 outage duration."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Healthy Baseline Suite", "scenario_type": "healthy_baseline", "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        body = start_res.json()
        assert body["status"] == "completed"
        assert body["results_summary"]["completed_runs"] == 5
        assert body["results_summary"]["total_outage_duration"]["mean"] == 0.0
        assert body["results_summary"]["false_positive_rate"] == 0.0
        assert body["results_summary"]["safety_compliance_rate"] == 100.0


@pytest.mark.asyncio
async def test_07_scenario_2_service_unavailable_recovery_enabled(db_session):
    """Verifies Scenario 2 with Recovery Enabled: simulated restart, health verified, low MTTR."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "503 Outage Enabled", "scenario_type": "service_unavailable", "recovery_enabled": True, "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        body = start_res.json()
        assert body["status"] == "completed"
        summary = body["results_summary"]
        assert summary["recovery_success_rate"] == 100.0
        assert summary["safety_compliance_rate"] == 100.0
        assert 1000.0 <= summary["detection_latency"]["mean"] <= 3000.0
        assert 1500.0 <= summary["recovery_duration"]["mean"] <= 4000.0
        assert summary["total_outage_duration"]["mean"] < 10000.0  # Much less than 60,000ms unmitigated!


@pytest.mark.asyncio
async def test_08_scenario_2_service_unavailable_recovery_disabled_control(db_session):
    """Verifies Scenario 2 with Recovery Disabled: unmitigated 60,000ms outage, no recovery attempted."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "503 Outage Control", "scenario_type": "service_unavailable", "recovery_enabled": False, "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        body = start_res.json()
        summary = body["results_summary"]
        assert summary["total_outage_duration"]["mean"] == 60000.0
        assert summary["recovery_duration"]["mean"] is None
        assert summary["recovery_duration"]["sample_count"] == 0


@pytest.mark.asyncio
async def test_09_scenario_3_high_error_rate_execution(db_session):
    """Verifies Scenario 3 (high error rate): threshold breach detected and simulated."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "High Error Rate Drill", "scenario_type": "high_error_rate", "number_of_runs": 3, "random_seed": 77},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        summary = start_res.json()["results_summary"]
        assert summary["completed_runs"] == 3
        assert summary["recovery_success_rate"] == 100.0
        assert summary["sample_size_warning"] is not None  # N=3 flags small sample warning!


@pytest.mark.asyncio
async def test_10_scenario_4_resource_exhaustion_execution(db_session):
    """Verifies Scenario 4 (resource exhaustion): CPU saturation and scale action simulated."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Resource Exhaustion", "scenario_type": "resource_exhaustion", "number_of_runs": 5, "random_seed": 99},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        runs_res = await ac.get(f"/api/v1/experiments/{exp_id}/runs", headers={"Authorization": f"Bearer {data['viewer_token']}"})
        runs = runs_res.json()
        assert len(runs) == 5
        assert all(r["recovery_success"] is True for r in runs)


@pytest.mark.asyncio
async def test_11_scenario_5_repeated_alerts_cooldown_suppression(db_session):
    """Verifies Scenario 5: flapping alerts suppressed by cooldown window."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Repeated Alerts Cooldown", "scenario_type": "repeated_alerts", "number_of_runs": 3, "random_seed": 105},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        runs = (await ac.get(f"/api/v1/experiments/{exp_id}/runs", headers={"Authorization": f"Bearer {data['viewer_token']}"})).json()
        assert len(runs) == 3
        # Check execution log for cooldown suppression entry
        first_run_logs = runs[0]["execution_log"]
        events = [log["event"] for log in first_run_logs]
        assert "cooldown_suppression" in events


@pytest.mark.asyncio
async def test_12_scenario_6_verification_failure_escalation_integrity(db_session):
    """Verifies Scenario 6: health check fails, recovery_success=False, incident escalated, NOT marked resolved."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Verification Failure Test", "scenario_type": "verification_failure", "number_of_runs": 5, "random_seed": 202},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        summary = start_res.json()["results_summary"]
        assert summary["recovery_success_rate"] == 0.0  # Verification failed
        assert summary["escalation_rate"] == 100.0  # Escalated to operator
        assert summary["safety_compliance_rate"] == 100.0  # Safety rule respected!


@pytest.mark.asyncio
async def test_13_scenario_7_unauthorized_recovery_block(db_session):
    """Verifies Scenario 7: unauthorized recovery attempt is blocked and safety compliant."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Unauthorized Block Test", "scenario_type": "unauthorized_recovery", "number_of_runs": 3, "random_seed": 303},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        summary = start_res.json()["results_summary"]
        assert summary["safety_compliance_rate"] == 100.0


@pytest.mark.asyncio
async def test_14_scenario_8_unapproved_recovery_held(db_session):
    """Verifies Scenario 8: destructive recovery missing sign-off is held and escalated."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Unapproved Hold Test", "scenario_type": "unapproved_recovery", "number_of_runs": 3, "random_seed": 404},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        summary = start_res.json()["results_summary"]
        assert summary["safety_compliance_rate"] == 100.0
        assert summary["escalation_rate"] == 100.0


def test_15_metric_distributions_and_sample_size_awareness():
    """Unit test for distribution statistics and small sample size flagging."""
    # N = 3 (small sample size)
    d3 = calculate_distribution([100.0, 200.0, 300.0], unit="ms")
    assert d3.sample_count == 3
    assert d3.small_sample_size is True
    assert d3.mean == 200.0
    assert d3.median == 200.0
    assert d3.min == 100.0
    assert d3.max == 300.0
    assert d3.std_dev == 100.0

    # N = 6 (adequate sample size)
    d6 = calculate_distribution([10.0, 20.0, 30.0, 40.0, 50.0, 60.0], unit="ms")
    assert d6.sample_count == 6
    assert d6.small_sample_size is False
    assert d6.mean == 35.0
    assert d6.median == 35.0

    # Empty list
    d0 = calculate_distribution([], unit="ms")
    assert d0.sample_count == 0
    assert d0.small_sample_size is True
    assert d0.mean is None


@pytest.mark.asyncio
async def test_16_pairwise_comparison_mttr_reduction(db_session):
    """Verifies side-by-side comparison between recovery enabled and control disabled."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create & run enabled experiment
        res_e = await ac.post(
            "/api/v1/experiments",
            json={"name": "Comparison Enabled", "scenario_type": "service_unavailable", "recovery_enabled": True, "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_e_id = res_e.json()["id"]
        await ac.post(f"/api/v1/experiments/{exp_e_id}/start", headers={"Authorization": f"Bearer {data['operator_token']}"})

        # Create & run disabled control experiment
        res_d = await ac.post(
            "/api/v1/experiments",
            json={"name": "Comparison Disabled", "scenario_type": "service_unavailable", "recovery_enabled": False, "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_d_id = res_d.json()["id"]
        await ac.post(f"/api/v1/experiments/{exp_d_id}/start", headers={"Authorization": f"Bearer {data['operator_token']}"})

        # Compare
        comp_res = await ac.get(
            f"/api/v1/experiments/{exp_e_id}/compare?control_experiment_id={exp_d_id}",
            headers={"Authorization": f"Bearer {data['viewer_token']}"},
        )
        assert comp_res.status_code == 200
        comp = comp_res.json()
        assert comp["outage_reduction_ms"] is not None
        assert comp["outage_reduction_percentage"] > 80.0  # Significant outage reduction!
        assert comp["is_statistically_significant"] is True
        assert "Autonomous recovery reduced mean outage duration" in comp["confidence_note"]


@pytest.mark.asyncio
async def test_17_experiment_cancellation(db_session):
    """Verifies that an experiment in pending state can be cancelled gracefully."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "To Be Cancelled", "scenario_type": "healthy_baseline"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        cancel_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/cancel",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_18_tenant_isolation(db_session):
    """Verifies that Tenant B cannot access or mutate Tenant A's experiments (404 Not Found)."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Org A Confidential Experiment", "scenario_type": "service_unavailable"},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        # Org B attempts to get Org A's experiment
        res_get = await ac.get(
            f"/api/v1/experiments/{exp_id}",
            headers={"Authorization": f"Bearer {data['org_b_token']}"},
        )
        assert res_get.status_code == 404

        # Org B attempts to start Org A's experiment
        res_start = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['org_b_token']}"},
        )
        assert res_start.status_code == 404


@pytest.mark.asyncio
async def test_19_research_report_pdf_export(db_session):
    """Verifies that the PDF report endpoint generates valid PDF bytes."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "PDF Report Subject", "scenario_type": "service_unavailable", "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]
        await ac.post(f"/api/v1/experiments/{exp_id}/start", headers={"Authorization": f"Bearer {data['operator_token']}"})

        pdf_res = await ac.get(
            f"/api/v1/experiments/{exp_id}/report?format=pdf",
            headers={"Authorization": f"Bearer {data['viewer_token']}"},
        )
        assert pdf_res.status_code == 200
        assert pdf_res.headers["Content-Type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF")
        assert len(pdf_res.content) > 1000


@pytest.mark.asyncio
async def test_20_research_report_json_export(db_session):
    """Verifies that the JSON report endpoint returns complete research methodology and data."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "JSON Report Subject", "scenario_type": "service_unavailable", "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]
        await ac.post(f"/api/v1/experiments/{exp_id}/start", headers={"Authorization": f"Bearer {data['operator_token']}"})

        json_res = await ac.get(
            f"/api/v1/experiments/{exp_id}/report?format=json",
            headers={"Authorization": f"Bearer {data['viewer_token']}"},
        )
        assert json_res.status_code == 200
        report = json_res.json()
        assert "report_metadata" in report
        assert "aggregate_analytics" in report
        assert "runs" in report
        assert "methodology" in report
        assert report["report_metadata"]["safety_mode"] == "RECOVERY_SIMULATION_MODE=true"
        assert len(report["runs"]) == 5


@pytest.mark.asyncio
async def test_21_prevent_stale_rerun_on_completed_experiment(db_session):
    """Verifies that an already completed experiment cannot be restarted, preventing stale result pollution."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_res = await ac.post(
            "/api/v1/experiments",
            json={"name": "Immutable Completed Suite", "scenario_type": "healthy_baseline", "number_of_runs": 2},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        exp_id = create_res.json()["id"]

        start_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert start_res.status_code == 200
        assert start_res.json()["status"] == "completed"

        # Re-start attempt must be rejected with 409 Conflict
        rerun_res = await ac.post(
            f"/api/v1/experiments/{exp_id}/start",
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        assert rerun_res.status_code == 409
        assert "already completed" in rerun_res.json()["detail"]


@pytest.mark.asyncio
async def test_22_audit_right_censored_control_and_evidence_tiers(db_session):
    """Verifies that control outages are zero-variance right-censored at 60s and evidence tiers are accurate."""
    data = await get_phase14_test_data(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Healthy baseline: SYNTHETIC tier
        res_h = await ac.post(
            "/api/v1/experiments",
            json={"name": "Healthy Baseline Tier Check", "scenario_type": "healthy_baseline", "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        h_id = res_h.json()["id"]
        start_h = await ac.post(f"/api/v1/experiments/{h_id}/start", headers={"Authorization": f"Bearer {data['operator_token']}"})
        h_summary = start_h.json()["results_summary"]
        assert h_summary["detection_latency"]["classification"] == "SYNTHETIC"

        # Service unavailable control: SIMULATED / CALCULATED tiers, right-censored at 60,000ms
        res_c = await ac.post(
            "/api/v1/experiments",
            json={"name": "Control Censoring Check", "scenario_type": "service_unavailable", "recovery_enabled": False, "number_of_runs": 5, "random_seed": 42},
            headers={"Authorization": f"Bearer {data['operator_token']}"},
        )
        c_id = res_c.json()["id"]
        start_c = await ac.post(f"/api/v1/experiments/{c_id}/start", headers={"Authorization": f"Bearer {data['operator_token']}"})
        c_summary = start_c.json()["results_summary"]
        assert c_summary["total_outage_duration"]["mean"] == 60000.0
        assert c_summary["total_outage_duration"]["std_dev"] == 0.0
        assert c_summary["total_outage_duration"]["classification"] == "CALCULATED"

        # Check run logs for right-censored flag
        runs_res = await ac.get(f"/api/v1/experiments/{c_id}/runs", headers={"Authorization": f"Bearer {data['viewer_token']}"})
        runs = runs_res.json()
        assert len(runs) == 5
        for r in runs:
            censored_logs = [log for log in r["execution_log"] if log.get("is_right_censored")]
            assert len(censored_logs) > 0

