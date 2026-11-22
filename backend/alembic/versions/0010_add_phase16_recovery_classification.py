"""Add Phase 16 recovery execution mode and evidence classification

Revision ID: 0010_add_phase16_recovery_classification
Revises: 0009_add_phase14_experiment_tables
Create Date: 2026-11-22 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010_add_phase16_recovery_classification"
down_revision: Union[str, None] = "0009_add_phase14_experiment_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. recovery_actions columns
    op.add_column(
        "recovery_actions",
        sa.Column("execution_mode", sa.String(length=50), server_default="SIMULATED", nullable=False),
    )
    op.add_column(
        "recovery_actions",
        sa.Column("evidence_classification", sa.String(length=50), server_default="SIMULATED", nullable=False),
    )

    # 2. recovery_results columns
    op.add_column(
        "recovery_results",
        sa.Column("execution_mode", sa.String(length=50), server_default="SIMULATED", nullable=False),
    )
    op.add_column(
        "recovery_results",
        sa.Column("evidence_classification", sa.String(length=50), server_default="SIMULATED", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("recovery_results", "evidence_classification")
    op.drop_column("recovery_results", "execution_mode")
    op.drop_column("recovery_actions", "evidence_classification")
    op.drop_column("recovery_actions", "execution_mode")
