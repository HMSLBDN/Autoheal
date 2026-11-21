"""Add Phase 14 experiment and benchmark evaluation tables

Revision ID: 0009_add_phase14_experiment_tables
Revises: 0008_add_phase13_pilot_tables
Create Date: 2026-11-22 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009_add_phase14_experiment_tables"
down_revision: Union[str, None] = "0008_add_phase13_pilot_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. experiments
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("scenario_type", sa.String(length=50), nullable=False),
        sa.Column("execution_mode", sa.String(length=50), server_default="SIMULATED", nullable=False),
        sa.Column("recovery_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("target_service_id", sa.String(length=100), server_default="checkout-api", nullable=False),
        sa.Column("number_of_runs", sa.Integer(), server_default="5", nullable=False),
        sa.Column("random_seed", sa.Integer(), server_default="42", nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("test_conditions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("results_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiments_organization_id", "experiments", ["organization_id"])
    op.create_index("ix_experiments_scenario_type", "experiments", ["scenario_type"])
    op.create_index("ix_experiments_status", "experiments", ["status"])

    # 2. experiment_runs
    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("experiment_id", sa.String(length=50), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("recovery_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("fault_injected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detection_latency_ms", sa.Float(), nullable=True),
        sa.Column("recovery_duration_ms", sa.Float(), nullable=True),
        sa.Column("total_outage_duration_ms", sa.Float(), nullable=True),
        sa.Column("recovery_attempted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("recovery_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("recovery_success", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_false_positive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("safety_compliant", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("escalated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=True),
        sa.Column("recovery_action_id", sa.String(length=50), nullable=True),
        sa.Column("evidence_classification", sa.String(length=50), server_default="SIMULATED", nullable=False),
        sa.Column("telemetry_samples", sa.JSON(), nullable=False),
        sa.Column("execution_log", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"])
    op.create_index("ix_experiment_runs_status", "experiment_runs", ["status"])


def downgrade() -> None:
    op.drop_table("experiment_runs")
    op.drop_table("experiments")
