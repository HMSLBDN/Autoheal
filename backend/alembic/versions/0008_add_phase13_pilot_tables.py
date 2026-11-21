"""Add Phase 13 organization invitations and incident lifecycle transition records

Revision ID: 0008_add_phase13_pilot_tables
Revises: 0007_add_phase10_security_tables
Create Date: 2026-11-21 19:50:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_add_phase13_pilot_tables"
down_revision: Union[str, None] = "0007_add_phase10_security_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. organization_invitations
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="operator", nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("is_accepted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_organization_invitations_org", "organization_invitations", ["organization_id"])
    op.create_index("ix_organization_invitations_email", "organization_invitations", ["email"])
    op.create_index("ix_organization_invitations_token_hash", "organization_invitations", ["token_hash"])

    # 2. incident_transitions
    op.create_table(
        "incident_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=50), nullable=False),
        sa.Column("previous_state", sa.String(length=50), nullable=False),
        sa.Column("new_state", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.String(length=50), nullable=True),
        sa.Column("sign_off", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_transitions_org", "incident_transitions", ["organization_id"])
    op.create_index("ix_incident_transitions_incident_id", "incident_transitions", ["incident_id"])
    op.create_index("ix_incident_transitions_created_at", "incident_transitions", ["created_at"])


def downgrade() -> None:
    op.drop_table("incident_transitions")
    op.drop_table("organization_invitations")
