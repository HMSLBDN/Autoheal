"""Add infrastructure_agents table and indexes

Revision ID: 0004_add_infrastructure_agents_table
Revises: 0003_add_production_performance_indexes
Create Date: 2026-11-21 13:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_add_infrastructure_agents_table"
down_revision: Union[str, None] = "0003_add_production_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_agents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("hostname", sa.String(length=100), nullable=False),
        sa.Column("ip_address", sa.String(length=50), nullable=False),
        sa.Column("environment", sa.String(length=50), server_default="production", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="online", nullable=False),
        sa.Column("version", sa.String(length=50), server_default="1.0.0", nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("public_key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("secret_key_hash", sa.String(length=64), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_infrastructure_agents_id", "infrastructure_agents", ["id"])
    op.create_index("ix_infrastructure_agents_org_id", "infrastructure_agents", ["organization_id"])
    op.create_index("ix_infrastructure_agents_env", "infrastructure_agents", ["environment"])
    op.create_index("ix_infrastructure_agents_status", "infrastructure_agents", ["status"])
    op.create_index("ix_agents_org_env", "infrastructure_agents", ["organization_id", "environment"])
    op.create_index("ix_agents_org_status", "infrastructure_agents", ["organization_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_agents_org_status", table_name="infrastructure_agents")
    op.drop_index("ix_agents_org_env", table_name="infrastructure_agents")
    op.drop_index("ix_infrastructure_agents_status", table_name="infrastructure_agents")
    op.drop_index("ix_infrastructure_agents_env", table_name="infrastructure_agents")
    op.drop_index("ix_infrastructure_agents_org_id", table_name="infrastructure_agents")
    op.drop_index("ix_infrastructure_agents_id", table_name="infrastructure_agents")
    op.drop_table("infrastructure_agents")
