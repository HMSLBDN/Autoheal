"""Add production composite performance indexes

Revision ID: 0003_add_production_performance_indexes
Revises: 0002_add_password_resets
Create Date: 2026-11-21 12:50:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_add_production_performance_indexes"
down_revision: Union[str, None] = "0002_add_password_resets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Incidents composite indexes: (organization_id, detected_at) and (organization_id, status)
    op.create_index(
        "ix_incidents_org_detected_at",
        "incidents",
        ["organization_id", "detected_at"],
    )
    op.create_index(
        "ix_incidents_org_status",
        "incidents",
        ["organization_id", "status"],
    )

    # 2. Services composite index: (organization_id, environment)
    op.create_index(
        "ix_services_org_env",
        "services",
        ["organization_id", "environment"],
    )

    # 3. Service metrics time-series composite index: (service_id, sampled_at)
    op.create_index(
        "ix_service_metrics_svc_sampled",
        "service_metrics",
        ["service_id", "sampled_at"],
    )

    # 4. Audit logs composite index: (organization_id, created_at)
    op.create_index(
        "ix_audit_logs_org_created",
        "audit_logs",
        ["organization_id", "created_at"],
    )

    # 5. Refresh tokens composite index: (user_id, is_revoked)
    op.create_index(
        "ix_refresh_tokens_user_revoked",
        "refresh_tokens",
        ["user_id", "is_revoked"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_revoked", table_name="refresh_tokens")
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
    op.drop_index("ix_service_metrics_svc_sampled", table_name="service_metrics")
    op.drop_index("ix_services_org_env", table_name="services")
    op.drop_index("ix_incidents_org_status", table_name="incidents")
    op.drop_index("ix_incidents_org_detected_at", table_name="incidents")
