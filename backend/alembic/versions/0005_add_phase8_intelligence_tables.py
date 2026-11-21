"""Add Phase 8 intelligence, anomaly detection, predictions, and risk scoring tables

Revision ID: 0005_add_phase8_intelligence_tables
Revises: 0004_add_infrastructure_agents_table
Create Date: 2026-11-21 15:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_add_phase8_intelligence_tables"
down_revision: Union[str, None] = "0004_add_infrastructure_agents_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. anomaly_events table
    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("metric_name", sa.String(length=50), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("z_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("anomaly_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("severity", sa.String(length=50), server_default="medium", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="detected", nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomaly_events_id", "anomaly_events", ["id"])
    op.create_index("ix_anomaly_events_org", "anomaly_events", ["organization_id"])
    op.create_index("ix_anomaly_events_svc", "anomaly_events", ["service_id"])
    op.create_index("ix_anomalies_org_detected", "anomaly_events", ["organization_id", "detected_at"])
    op.create_index("ix_anomalies_svc_metric", "anomaly_events", ["service_id", "metric_name"])

    # 2. predictive_insights table
    op.create_table(
        "predictive_insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("metric_name", sa.String(length=50), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("prediction_horizon_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("risk_level", sa.String(length=50), server_default="medium", nullable=False),
        sa.Column("anomaly_probability", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("algorithm", sa.String(length=100), nullable=False),
        sa.Column("supporting_evidence_json", sa.Text(), nullable=False),
        sa.Column("recommended_preventive_action", sa.Text(), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictive_insights_id", "predictive_insights", ["id"])
    op.create_index("ix_predictions_org_svc", "predictive_insights", ["organization_id", "service_id"])
    op.create_index("ix_predictions_target_time", "predictive_insights", ["target_time"])

    # 3. service_risk_scores table
    op.create_table(
        "service_risk_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("risk_score", sa.Float(), server_default="10.0", nullable=False),
        sa.Column("risk_category", sa.String(length=50), server_default="low", nullable=False),
        sa.Column("contributing_factors_json", sa.Text(), nullable=False),
        sa.Column("cpu_trend", sa.String(length=50), server_default="stable", nullable=False),
        sa.Column("memory_trend", sa.String(length=50), server_default="stable", nullable=False),
        sa.Column("incident_frequency_7d", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_recoveries_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recent_deployment_flag", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_risk_scores_id", "service_risk_scores", ["id"])
    op.create_index("ix_service_risk_org_svc", "service_risk_scores", ["organization_id", "service_id"])
    op.create_index("ix_service_risk_calculated", "service_risk_scores", ["calculated_at"])

    # 4. incident_correlations table
    op.create_table(
        "incident_correlations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_group_id", sa.String(length=100), nullable=False),
        sa.Column("primary_incident_id", sa.String(length=50), nullable=False),
        sa.Column("correlated_incident_id", sa.String(length=50), nullable=False),
        sa.Column("correlation_score", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("correlation_type", sa.String(length=50), server_default="temporal", nullable=False),
        sa.Column("shared_evidence_json", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["primary_incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["correlated_incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_correlations_id", "incident_correlations", ["id"])
    op.create_index("ix_correlations_group", "incident_correlations", ["correlation_group_id"])
    op.create_index("ix_correlations_primary", "incident_correlations", ["primary_incident_id"])

    # 5. preventive_recommendations table
    op.create_table(
        "preventive_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=50), server_default="medium", nullable=False),
        sa.Column("risk_level", sa.String(length=50), server_default="medium", nullable=False),
        sa.Column("category", sa.String(length=100), server_default="capacity_growth", nullable=False),
        sa.Column("supporting_evidence_json", sa.Text(), nullable=False),
        sa.Column("expected_benefit", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_preventive_recommendations_id", "preventive_recommendations", ["id"])
    op.create_index("ix_recommendations_org_status", "preventive_recommendations", ["organization_id", "status"])
    op.create_index("ix_recommendations_svc", "preventive_recommendations", ["service_id"])

    # 6. model_evaluation_records table
    op.create_table(
        "model_evaluation_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("evaluation_type", sa.String(length=100), nullable=False),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("precision", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("recall", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("f1_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("false_positive_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("false_negative_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("mean_absolute_error", sa.Float(), nullable=True),
        sa.Column("mean_latency_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_evaluation_records_id", "model_evaluation_records", ["id"])
    op.create_index("ix_model_eval_name_date", "model_evaluation_records", ["model_name", "evaluated_at"])


def downgrade() -> None:
    op.drop_table("model_evaluation_records")
    op.drop_table("preventive_recommendations")
    op.drop_table("incident_correlations")
    op.drop_table("service_risk_scores")
    op.drop_table("predictive_insights")
    op.drop_table("anomaly_events")
